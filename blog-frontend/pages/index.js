import Head from 'next/head'
import { useState, useEffect } from 'react'
import Layout from '../components/Layout'
import PostCard from '../components/PostCard'
import { getPosts, getCategories, getTags } from '../lib/ghost'

export default function Home({ posts, categories, tags }) {
  const [activeCategory, setActiveCategory] = useState(null)
  const [activeTag, setActiveTag] = useState(null)
  const [filteredPosts, setFilteredPosts] = useState(posts)

  useEffect(() => {
    setFilteredPosts(posts)
  }, [posts])

  const handleCategoryFilter = (categorySlug) => {
    if (activeCategory === categorySlug) {
      setActiveCategory(null)
    } else {
      setActiveCategory(categorySlug)
    }
    setActiveTag(null)
  }

  const handleTagFilter = (tagSlug) => {
    if (activeTag === tagSlug) {
      setActiveTag(null)
    } else {
      setActiveTag(tagSlug)
    }
    setActiveCategory(null)
  }

  const getFilteredPosts = () => {
    let result = posts

    if (activeCategory) {
      result = result.filter(post => 
        post.primary_category?.slug === activeCategory
      )
    }

    if (activeTag) {
      result = result.filter(post =>
        post.tags?.some(tag => tag.slug === activeTag)
      )
    }

    return result
  }

  const displayPosts = getFilteredPosts()

  return (
    <Layout>
      <Head>
        <title>Medium Blog - Thoughtful Stories</title>
        <meta name="description" content="A Medium-style blog powered by Ghost CMS" />
      </Head>

      <section className="hero">
        <h1>Thoughtful Stories</h1>
        <p>Explore ideas, insights, and stories that matter. A space for curious minds.</p>
      </section>

      <section className="filters">
        <div className="filter-group">
          <span className="filter-label">Category:</span>
          {categories.slice(0, 5).map(category => (
            <button
              key={category.id}
              className={`filter-btn ${activeCategory === category.slug ? 'active' : ''}`}
              onClick={() => handleCategoryFilter(category.slug)}
            >
              {category.name}
            </button>
          ))}
        </div>
        <div className="filter-group">
          <span className="filter-label">Tags:</span>
          {tags.slice(0, 5).map(tag => (
            <button
              key={tag.id}
              className={`filter-btn ${activeTag === tag.slug ? 'active' : ''}`}
              onClick={() => handleTagFilter(tag.slug)}
            >
              {tag.name}
            </button>
          ))}
        </div>
      </section>

      {displayPosts.length > 0 ? (
        <div className="posts-grid">
          {displayPosts.map(post => (
            <PostCard key={post.id} post={post} />
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <h2>No posts found</h2>
          <p>Try adjusting your filters or check back later.</p>
        </div>
      )}
    </Layout>
  )
}

export async function getServerSideProps() {
  const posts = await getPosts()
  const categories = await getCategories()
  const tags = await getTags()

  return {
    props: {
      posts: posts || [],
      categories: categories || [],
      tags: tags || []
    }
  }
}
