#!/usr/bin/env python3
"""
Workflow Agent Service
A self-contained background service that:
1. Consumes messages from AWS SQS queue
2. Processes them through the Workflow Management Agent
3. Runs as a daemon/background service

Usage:
    python agent_service.py                    # Run in foreground (interactive)
    python agent_service.py --daemon           # Run as background daemon
    python agent_service.py --mode sqs         # SQS consumer mode only
    python agent_service.py --mode cli         # CLI interactive mode only
    python agent_service.py --mode both        # Both SQS and CLI (default)
"""

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

from app.utils.security import sanitize_log_input

# ============================================================
# Configuration
# ============================================================

# Load environment variables
env_path = Path(__file__).parent / ".env"
env_dev_path = Path(__file__).parent / ".env_dev"

if env_path.exists():
    load_dotenv(env_path)
elif env_dev_path.exists():
    load_dotenv(env_dev_path)

# Service Configuration
SERVICE_NAME = "WorkflowAgentService"
PID_FILE = Path(__file__).parent / "agent_service.pid"
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# ============================================================
# Logging Setup
# ============================================================

RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILENAME = LOGS_DIR / f"agent_service_{RUN_TIMESTAMP}.log"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILENAME, encoding='utf-8')
    ]
)

logger = logging.getLogger("agent_service")


# ============================================================
# Service Class
# ============================================================

class WorkflowAgentService:
    """
    Background service that integrates SQS message consumption with the Workflow Agent
    """
    
    def __init__(
        self,
        mode: str = "both",
        queue_name: Optional[str] = None,
        auto_delete: bool = True
    ):
        """
        Initialize the agent service
        
        Args:
            mode: 'sqs', 'cli', or 'both'
            queue_name: SQS queue name (uses config default if not provided)
            auto_delete: Whether to auto-delete processed SQS messages
        """
        self.mode = mode
        self.queue_name = queue_name
        self.auto_delete = auto_delete
        self.running = False
        self.sqs_thread = None
        self.cli_thread = None
        
        # Import agent components
        self._import_agent()
        
        # Import SQS consumer
        self._import_sqs_consumer()
        
        logger.info(f"✅ {SERVICE_NAME} initialized")
        logger.info(f"   Mode: {sanitize_log_input(mode)}")
        logger.info(f"   Log file: {sanitize_log_input(str(LOG_FILENAME))}")
    
    def _import_agent(self):
        """Import the API agent module"""
        try:
            from api_agent import run_agent, run_agent_rule_based, logger as agent_logger
            self.run_agent = run_agent
            self.run_agent_rule_based = run_agent_rule_based
            logger.info("✅ API Agent imported successfully")
        except ImportError as e:
            # Handle specific LangChain dependency issues gracefully
            if "langchain" in str(e):
                logger.error(f"❌ Failed to import API Agent: {sanitize_log_input(str(e))}")
                logger.warning("   Please ensure langchain packages are installed:")
                logger.warning("   poetry add langchain-anthropic langchain-openai langchain-core")
            else:
                logger.error(f"❌ Failed to import API Agent: {sanitize_log_input(str(e))}")
            self.run_agent = None
            self.run_agent_rule_based = None
    
    def _import_sqs_consumer(self):
        """Import the SQS consumer module"""
        try:
            from sqs_consumer import (
                SQSMessageConsumer,
                load_aws_config,
                create_consumer_from_config
            )
            self.SQSMessageConsumer = SQSMessageConsumer
            self.load_aws_config = load_aws_config
            self.create_consumer_from_config = create_consumer_from_config
            
            # Load config to get default queue name
            config = load_aws_config()
            if config and not self.queue_name:
                self.queue_name = config.get('resources', {}).get('sqs_queue', 'workflow_orchestrator_queue.fifo')
            
            logger.info("✅ SQS Consumer imported successfully")
        except ImportError as e:
            # Handle boto3 dependency issues gracefully
            if "boto3" in str(e):
                logger.error(f"❌ Failed to import SQS Consumer: {sanitize_log_input(str(e))}")
                logger.warning("   Please ensure boto3 is installed:")
                logger.warning("   poetry add boto3")
            else:
                logger.error(f"❌ Failed to import SQS Consumer: {sanitize_log_input(str(e))}")
            self.SQSMessageConsumer = None
    
    def _handle_sqs_message(self, message_content: str) -> dict:
        """
        Handle incoming SQS message by passing it to the agent
        
        Args:
            message_content: The message content/command
            
        Returns:
            Agent response
        """
        if self.run_agent:
            logger.info(f"🤖 Processing through agent: {sanitize_log_input(message_content)[:100]}...")
            return self.run_agent(message_content)
        else:
            logger.warning("⚠️ Agent not available, using rule-based fallback")
            if self.run_agent_rule_based:
                return self.run_agent_rule_based(message_content)
            return {"status": "error", "message": "Agent not available"}
    
    def _run_sqs_consumer(self):
        """Run the SQS consumer in a thread"""
        if not self.SQSMessageConsumer:
            logger.error("❌ SQS Consumer not available")
            return
        
        try:
            consumer = self.create_consumer_from_config(
                message_handler=self._handle_sqs_message
            )
            
            if not consumer:
                logger.error("❌ Failed to create SQS consumer from config")
                return
            
            logger.info(f"📡 Starting SQS consumer for queue: {sanitize_log_input(self.queue_name)}")
            
            while self.running:
                try:
                    consumer.consume_continuously(
                        queue_name=self.queue_name,
                        auto_delete=self.auto_delete,
                        max_messages=10,
                        wait_time_seconds=20
                    )
                except Exception as e:
                    if self.running:
                        logger.error(f"❌ SQS consumer error: {sanitize_log_input(str(e))}")
                        time.sleep(5)  # Wait before retry
                    else:
                        break
            
            consumer.print_stats()
            
        except Exception as e:
            logger.error(f"❌ Fatal SQS consumer error: {sanitize_log_input(str(e))}")
    
    def _run_cli(self):
        """Run the interactive CLI in a thread"""
        if not self.run_agent:
            logger.error("❌ Agent not available for CLI")
            return
        
        print("\n" + "="*60)
        print(f"{SERVICE_NAME} - Interactive CLI")
        print("="*60)
        print("\nCommands you can try:")
        print("  - 'list reports' or 'show all'")
        print("  - 'status of RPT-001'")
        print("  - 'accept RPT-001'")
        print("  - 'reject RPT-001'")
        print("  - 'create report for credit opinion'")
        print("  - 'quit' or 'exit' to stop")
        print("-"*60 + "\n")
        
        while self.running:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    logger.info("CLI session ended by user")
                    self.stop()
                    break
                
                logger.info(f"[CLI] User input: {sanitize_log_input(user_input)}")
                result = self.run_agent(user_input)
                logger.info(f"[CLI] Agent response: {sanitize_log_input(json.dumps(result, default=str))}")
                
                print(f"\nAgent: {json.dumps(result, indent=2, default=str)}\n")
                
            except EOFError:
                # Handle daemon mode where stdin is not available
                logger.info("CLI stdin closed, switching to SQS-only mode")
                break
            except KeyboardInterrupt:
                logger.info("CLI interrupted")
                self.stop()
                break
            except Exception as e:
                logger.error(f"CLI error: {sanitize_log_input(str(e))}")
    
    def start(self):
        """Start the service"""
        self.running = True
        logger.info(f"🚀 Starting {SERVICE_NAME}...")
        
        # Write PID file
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"   PID: {os.getpid()}")
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Start threads based on mode
        if self.mode in ['sqs', 'both']:
            self.sqs_thread = threading.Thread(target=self._run_sqs_consumer, name="SQS-Consumer")
            self.sqs_thread.daemon = True
            self.sqs_thread.start()
            logger.info("✅ SQS consumer thread started")
        
        if self.mode in ['cli', 'both']:
            # CLI runs in main thread for input handling
            self._run_cli()
        else:
            # Keep main thread alive for SQS-only mode
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stop()
    
    def stop(self):
        """Stop the service gracefully"""
        logger.info(f"🛑 Stopping {SERVICE_NAME}...")
        self.running = False
        
        # Remove PID file
        if PID_FILE.exists():
            PID_FILE.unlink()
        
        logger.info(f"✅ {SERVICE_NAME} stopped")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {sanitize_log_input(str(signum))}")
        self.stop()
        sys.exit(0)


# ============================================================
# Daemon Functions
# ============================================================

def daemonize():
    """
    Daemonize the process (Unix-like systems only)
    """
    if sys.platform == 'win32':
        logger.warning("⚠️ Daemon mode not fully supported on Windows")
        logger.warning("   Running in foreground mode instead")
        return
    
    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        logger.error(f"Fork #1 failed: {sanitize_log_input(str(e))}")
        sys.exit(1)
    
    # Decouple from parent environment
    os.chdir('/')
    os.setsid()
    os.umask(0)
    
    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        logger.error(f"Fork #2 failed: {sanitize_log_input(str(e))}")
        sys.exit(1)
    
    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    
    with open('/dev/null', 'r') as dev_null:
        os.dup2(dev_null.fileno(), sys.stdin.fileno())
    
    # Keep stdout and stderr for logging
    log_file = open(LOG_FILENAME, 'a')
    os.dup2(log_file.fileno(), sys.stdout.fileno())
    os.dup2(log_file.fileno(), sys.stderr.fileno())


def check_running() -> Optional[int]:
    """
    Check if service is already running
    
    Returns:
        PID if running, None otherwise
    """
    if PID_FILE.exists():
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            
            # Check if process is running
            if sys.platform == 'win32':
                import subprocess
                result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True)
                if str(pid) in result.stdout:
                    return pid
            else:
                os.kill(pid, 0)
                return pid
        except (OSError, ValueError, ProcessLookupError):
            # Process not running, clean up stale PID file
            PID_FILE.unlink()
    
    return None


def stop_service():
    """Stop a running service"""
    pid = check_running()
    if pid:
        logger.info(f"Stopping service with PID {pid}...")
        try:
            if sys.platform == 'win32':
                import subprocess
                subprocess.run(['taskkill', '/F', '/PID', str(pid)])
            else:
                os.kill(pid, signal.SIGTERM)
            
            # Wait for process to stop
            for _ in range(10):
                time.sleep(0.5)
                if not check_running():
                    logger.info("✅ Service stopped")
                    return True
            
            logger.warning("⚠️ Service did not stop gracefully, forcing...")
            if sys.platform != 'win32':
                os.kill(pid, signal.SIGKILL)
            return True
        except Exception as e:
            logger.error(f"❌ Failed to stop service: {sanitize_log_input(str(e))}")
            return False
    else:
        logger.info("Service is not running")
        return True


# ============================================================
# Main Entry Point
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=f"{SERVICE_NAME} - Background service for Workflow Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python agent_service.py                    # Run in foreground (interactive)
  python agent_service.py --daemon           # Run as background daemon
  python agent_service.py --mode sqs         # SQS consumer mode only
  python agent_service.py --mode cli         # CLI interactive mode only
  python agent_service.py --stop             # Stop running service
  python agent_service.py --status           # Check service status
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['sqs', 'cli', 'both'],
        default='both',
        help='Service mode: sqs (consume SQS only), cli (interactive only), both (default)'
    )
    parser.add_argument(
        '--daemon', '-d',
        action='store_true',
        help='Run as background daemon'
    )
    parser.add_argument(
        '--queue',
        help='SQS queue name (uses config default if not specified)'
    )
    parser.add_argument(
        '--no-delete',
        action='store_true',
        help='Do not delete messages after processing'
    )
    parser.add_argument(
        '--stop',
        action='store_true',
        help='Stop running service'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Check service status'
    )
    parser.add_argument(
        '--restart',
        action='store_true',
        help='Restart the service'
    )
    
    args = parser.parse_args()
    
    # Handle status check
    if args.status:
        pid = check_running()
        if pid:
            print(f"✅ {SERVICE_NAME} is running (PID: {pid})")
        else:
            print(f"⚠️ {SERVICE_NAME} is not running")
        return
    
    # Handle stop
    if args.stop:
        stop_service()
        return
    
    # Handle restart
    if args.restart:
        stop_service()
        time.sleep(1)
    
    # Check if already running
    pid = check_running()
    if pid:
        print(f"⚠️ {SERVICE_NAME} is already running (PID: {pid})")
        print("   Use --stop to stop it first, or --restart to restart")
        return
    
    # Daemon mode
    if args.daemon:
        print(f"🚀 Starting {SERVICE_NAME} as daemon...")
        print(f"   Log file: {LOG_FILENAME}")
        daemonize()
        # In daemon mode, force SQS-only mode (no CLI)
        args.mode = 'sqs'
    
    # Create and start service
    service = WorkflowAgentService(
        mode=args.mode,
        queue_name=args.queue,
        auto_delete=not args.no_delete
    )
    
    try:
        service.start()
    except Exception as e:
        logger.error(f"❌ Service error: {sanitize_log_input(str(e))}")
        service.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()

