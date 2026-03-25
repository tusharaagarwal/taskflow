import { useState, useEffect } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE || 'https://backend-production-701b.up.railway.app/api/v1'

console.log('API_BASE:', API_BASE)

interface Task {
  id: number
  title: string
  description: string | null
  status: 'todo' | 'in_progress' | 'done' | 'archived'
  priority: number
  due_date: string | null
  owner_id: number
  created_at: string
  updated_at: string
}

function Login({ onLogin }: { onLogin: (token: string) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({
          username: email,
          password,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Login failed')
      }
      const token = data.access_token
      localStorage.setItem('token', token)
      onLogin(token)
    } catch (err: any) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <form onSubmit={handleSubmit} className="bg-white p-8 rounded-lg shadow-md w-96 space-y-4">
        <h2 className="text-2xl font-bold text-center">TaskFlow Login</h2>
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <div>
          <label className="block text-sm font-medium mb-1">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full p-2 border rounded"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full p-2 border rounded"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition disabled:opacity-50"
        >
          {loading ? 'Logging in...' : 'Login'}
        </button>
        <p className="text-xs text-gray-500 text-center">Don't have an account? Register via API docs: /docs</p>
      </form>
    </div>
  )
}

function TaskList({ onLogout }: { onLogout: () => void }) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [saving, setSaving] = useState(false)

  const token = localStorage.getItem('token')

  useEffect(() => {
    fetchTasks()
  }, [])

  const fetchTasks = async () => {
    try {
      const res = await fetch(`${API_BASE}/tasks/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (!res.ok) throw new Error('Failed to fetch tasks')
      const data = await res.json()
      setTasks(data)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const createTask = async (title: string) => {
    setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/tasks/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title, status: 'todo' }),
      })
      if (!res.ok) throw new Error('Failed to create task')
      await fetchTasks()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleAddTask = (e: React.FormEvent) => {
    e.preventDefault()
    if (newTaskTitle.trim()) {
      createTask(newTaskTitle)
      setNewTaskTitle('')
    }
  }

  const cycleStatus = async (task: Task) => {
    const statusOrder: Task['status'][] = ['todo', 'in_progress', 'done', 'archived']
    const currentIndex = statusOrder.indexOf(task.status)
    const nextStatus = statusOrder[(currentIndex + 1) % statusOrder.length]
    
    try {
      await fetch(`${API_BASE}/tasks/${task.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ status: nextStatus }),
      })
      await fetchTasks()
    } catch (err: any) {
      setError(err.message)
    }
  }

  const deleteTask = async (id: number) => {
    try {
      await fetch(`${API_BASE}/tasks/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      await fetchTasks()
    } catch (err: any) {
      setError(err.message)
    }
  }

  if (loading) return <div className="p-8 text-center">Loading tasks...</div>
  if (error) return <div className="p-8 text-center text-red-500">Error: {error}</div>

  const tasksByStatus = {
    todo: tasks?.filter(t => t.status === 'todo') || [],
    in_progress: tasks?.filter(t => t.status === 'in_progress') || [],
    done: tasks?.filter(t => t.status === 'done') || [],
    archived: tasks?.filter(t => t.status === 'archived') || [],
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold">TaskFlow Dashboard</h1>
          <button
            onClick={onLogout}
            className="bg-red-500 text-white px-4 py-2 rounded hover:bg-red-600"
          >
            Logout
          </button>
        </div>

        <form onSubmit={handleAddTask} className="bg-white p-6 rounded-lg shadow mb-8 flex gap-2">
          <input
            type="text"
            value={newTaskTitle}
            onChange={(e) => setNewTaskTitle(e.target.value)}
            placeholder="New task title..."
            className="flex-1 p-3 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={saving}
            className="bg-blue-600 text-white px-6 py-3 rounded hover:bg-blue-700 transition disabled:opacity-50"
          >
            {saving ? 'Adding...' : 'Add'}
          </button>
        </form>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          {(['todo', 'in_progress', 'done', 'archived'] as const).map(status => (
            <div key={status} className="bg-white rounded-lg shadow p-4">
              <h2 className="text-lg font-semibold mb-4 capitalize text-gray-700">
                {status.replace('_', ' ')} ({tasksByStatus[status].length})
              </h2>
              <div className="space-y-3">
                {tasksByStatus[status].map(task => (
                  <div key={task.id} className="border rounded p-3 hover:shadow transition group">
                    <div className="flex justify-between items-start">
                      <h3 className="font-medium">{task.title}</h3>
                      <span className={`text-xs px-2 py-1 rounded ${
                        task.priority === 1 ? 'bg-red-100 text-red-700' :
                        task.priority === 2 ? 'bg-yellow-100 text-yellow-700' :
                        'bg-green-100 text-green-700'
                      }`}>
                        {task.priority === 1 ? 'High' : task.priority === 2 ? 'Medium' : 'Low'}
                      </span>
                    </div>
                    {task.description && (
                      <p className="text-sm text-gray-600 mt-2">{task.description}</p>
                    )}
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={() => cycleStatus(task)}
                        className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded hover:bg-blue-200 transition"
                      >
                        Cycle: {task.status.replace('_', ' ')}
                      </button>
                      <button
                        onClick={() => deleteTask(task.id)}
                        className="text-xs bg-red-100 text-red-700 px-2 py-1 rounded hover:bg-red-200 transition"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
                {tasksByStatus[status].length === 0 && (
                  <p className="text-sm text-gray-400 italic">No tasks</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'))

  const handleLogout = () => {
    localStorage.removeItem('token')
    setToken(null)
  }

  // Debug: Log token status
  useEffect(() => {
    console.log('Token present:', !!token)
  }, [token])

  return token ? <TaskList onLogout={handleLogout} /> : <Login onLogin={setToken} />
}

export default App
