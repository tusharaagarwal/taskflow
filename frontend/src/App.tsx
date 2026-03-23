import { useState, useEffect } from 'react'
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from 'react-query'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

const queryClient = new QueryClient()

const api = axios.create({
  baseURL: API_BASE,
})

// Types
interface User {
  id: number
  email: string
  full_name: string | null
  is_active: boolean
}

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const res = await api.post('/auth/login', new URLSearchParams({
        username: email,
        password,
      }))
      const token = res.data.access_token
      localStorage.setItem('token', token)
      onLogin(token)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed')
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
          className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition"
        >
          Login
        </button>
        <p className="text-xs text-gray-500 text-center">Don't have an account? Register via API docs: /docs</p>
      </form>
    </div>
  )
}

function TaskList() {
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const queryClient = useQueryClient()

  const { data: tasks, isLoading, error } = useQuery<Task[], Error>(
    'tasks',
    async () => {
      const res = await api.get('/tasks/')
      return res.data
    }
  )

  const createMutation = useMutation(
    async (title: string) => {
      const res = await api.post('/tasks/', { title, status: 'todo' })
      return res.data
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries('tasks')
      }
    }
  )

  const updateMutation = useMutation(
    async ({ id, updates }: { id: number; updates: Partial<Task> }) => {
      const res = await api.put(`/tasks/${id}`, updates)
      return res.data
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries('tasks')
      }
    }
  )

  const deleteMutation = useMutation(
    async (id: number) => {
      await api.delete(`/tasks/${id}`)
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries('tasks')
      }
    }
  )

  const handleAddTask = (e: React.FormEvent) => {
    e.preventDefault()
    if (newTaskTitle.trim()) {
      createMutation.mutate(newTaskTitle)
      setNewTaskTitle('')
    }
  }

  const cycleStatus = (task: Task) => {
    const statusOrder: Task['status'][] = ['todo', 'in_progress', 'done', 'archived']
    const currentIndex = statusOrder.indexOf(task.status)
    const nextStatus = statusOrder[(currentIndex + 1) % statusOrder.length]
    updateMutation.mutate({ id: task.id, updates: { status: nextStatus } })
  }

  if (isLoading) return <div className="p-8 text-center">Loading tasks...</div>
  if (error) return <div className="p-8 text-center text-red-500">Error loading tasks: {error.message}</div>

  const tasksByStatus = {
    todo: tasks?.filter(t => t.status === 'todo') || [],
    in_progress: tasks?.filter(t => t.status === 'in_progress') || [],
    done: tasks?.filter(t => t.status === 'done') || [],
    archived: tasks?.filter(t => t.status === 'archived') || [],
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">TaskFlow Dashboard</h1>

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
            disabled={createMutation.isLoading}
            className="bg-blue-600 text-white px-6 py-3 rounded hover:bg-blue-700 transition disabled:opacity-50"
          >
            Add
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
                        title="Change status"
                      >
                        Cycle: {task.status.replace('_', ' ')}
                      </button>
                      <button
                        onClick={() => deleteMutation.mutate(task.id)}
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

  useEffect(() => {
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`
    } else {
      delete api.defaults.headers.common['Authorization']
    }
  }, [token])

  return (
    <QueryClientProvider client={queryClient}>
      {token ? <TaskList /> : <Login onLogin={setToken} />}
    </QueryClientProvider>
  )
}

export default App