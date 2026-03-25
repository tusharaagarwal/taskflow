import Head from 'next/head'
import { useRouter } from 'next/router'
import { useState, useEffect } from 'react'
import Layout from '../components/Layout'
import PostCard from '../components/PostCard'
import { searchPosts } from '../lib/ghost'

export default function SearchPage({ initialQuery }) {
  const router = useRouter()
  const [query, setQuery] = useState(initialQuery || '')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (router.query.q) {
      setQuery(router.query.q)
      performSearch(router.query.q)
    }
  }, [router.query.q])

  const performSearch = async (searchQuery) => {
    if (!searchQuery) return
    setLoading(true)
    const posts = await searchPosts(searchQuery)
    setResults(posts)
    setLoading(false)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (query.trim()) {
      router.push(`/search?q=${encodeURIComponent(query.trim())}`)
    }
  }

  return (
    <Layout>
      <Head>
        <title>{query ? `Search: ${query}` : 'Search'} - Medium Blog</title>
      </Head>

      <section className="hero">
        <h1>Search</h1>
        <form onSubmit={handleSubmit} style={{ marginTop: '1rem' }}>
          <input
            type="text"
            placeholder="Search for posts..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="search-input"
            style={{ width: '300px', padding: '0.75rem 1rem' }}
          />
        </form>
      </section>

      {loading ? (
        <div className="loading">Searching...</div>
      ) : results.length > 0 ? (
        <>
          <p style={{ marginBottom: '2rem', color: 'var(--color-secondary)' }}>
            Found {results.length} result{results.length !== 1 ? 's' : ''} for "{query}"
          </p>
          <div className="posts-grid">
            {results.map(post => (
              <PostCard key={post.id} post={post} />
            ))}
          </div>
        </>
      ) : query ? (
        <div className="empty-state">
          <h2>No results found</h2>
          <p>Try different keywords or browse all posts.</p>
        </div>
      ) : null}
    </Layout>
  )
}

export async function getServerSideProps({ query }) {
  return {
    props: {
      initialQuery: query.q || ''
    }
  }
}

