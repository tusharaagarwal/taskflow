import Link from 'next/link'
import { useState } from 'react'
import { useRouter } from 'next/router'

export default function Layout({ children }) {
  const [searchQuery, setSearchQuery] = useState('')
  const router = useRouter()

  const handleSearch = (e) => {
    e.preventDefault()
    if (searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`)
      setSearchQuery('')
    }
  }

  return (
    <div>
      <header className="header">
        <div className="header-inner">
          <Link href="/" className="logo">
            Medium Blog
          </Link>
          <nav className="nav">
            <ul className="nav-links">
              <li><Link href="/">Home</Link></li>
              <li><Link href="/categories">Categories</Link></li>
              <li><Link href="/tags">Tags</Link></li>
            </ul>
            <form onSubmit={handleSearch} className="search-container">
              <input
                type="text"
                placeholder="Search posts..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="search-input"
              />
            </form>
          </nav>
        </div>
      </header>
      <main className="main">
        {children}
      </main>
      <footer className="footer">
        <p>Powered by Ghost CMS & Next.js</p>
      </footer>
    </div>
  )
}

