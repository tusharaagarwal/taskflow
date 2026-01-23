"""
Workflow action types for report tracker updates.

This module defines the centralized enum for all workflow action types,
providing a single source of truth for action mapping and validation.
"""
from enum import Enum
from typing import Set


class WorkflowActionType(str, Enum):
    """
    Enum for workflow action types in report tracker updates.
    
    Actions are categorized into two groups:
    - Forward Actions: Move workflow to success_goto (next step)
    - Backward Actions: Move workflow to fail_goto (previous step)
    """
    
    # Forward actions (move to success_goto)
    ACCEPT = "accept"      # Legacy - kept for backward compatibility
    SUBMIT = "submit"      # New semantic action
    APPROVE = "approve"    # New semantic action
    
    # Backward actions (move to fail_goto)
    REJECT = "reject"      # Legacy - kept for backward compatibility
    PUSH_BACK = "push_back"    # New semantic action
    PULL_BACK = "pull_back"    # New semantic action
    
    # Special actions (no-op, for future implementation)
    # TBD: To be discussed
    PUBLISH = "publish"              # TBD: Implementation to be discussed
    RAISE_EXEMPTION = "raise_exemption"  # TBD: Implementation to be discussed
    
    @classmethod
    def get_forward_actions(cls) -> Set[str]:
        """
        Get all forward navigation actions.
        
        Returns:
            Set of action values that move workflow forward
        """
        return {cls.ACCEPT.value, cls.SUBMIT.value, cls.APPROVE.value}
    
    @classmethod
    def get_backward_actions(cls) -> Set[str]:
        """
        Get all backward navigation actions.
        
        Returns:
            Set of action values that move workflow backward
        """
        return {cls.REJECT.value, cls.PUSH_BACK.value, cls.PULL_BACK.value}
    
    @classmethod
    def is_forward_action(cls, action: str) -> bool:
        """
        Check if action moves workflow forward.
        
        Args:
            action: Action string to check
            
        Returns:
            True if action is a forward navigation action
        """
        return action in cls.get_forward_actions()
    
    @classmethod
    def is_backward_action(cls, action: str) -> bool:
        """
        Check if action moves workflow backward.
        
        Args:
            action: Action string to check
            
        Returns:
            True if action is a backward navigation action
        """
        return action in cls.get_backward_actions()
    
    @classmethod
    def get_special_actions(cls) -> Set[str]:
        """
        Get all special/placeholder actions that don't change workflow state.
        TBD: These actions need implementation discussion.
        
        Returns:
            Set of action values that are placeholders
        """
        return {cls.PUBLISH.value, cls.RAISE_EXEMPTION.value}
    
    @classmethod
    def is_special_action(cls, action: str) -> bool:
        """
        Check if action is a special/placeholder action.
        TBD: Implementation to be discussed.
        
        Args:
            action: Action string to check
            
        Returns:
            True if action is a special action
        """
        return action in cls.get_special_actions()
    
    @classmethod
    def get_all_actions(cls) -> Set[str]:
        """
        Get all valid action values.
        
        Returns:
            Set of all valid action values
        """
        return cls.get_forward_actions() | cls.get_backward_actions() | cls.get_special_actions()

