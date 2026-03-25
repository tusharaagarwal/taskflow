import Head from 'next/head'
import Link from 'next/link'
import Layout from '../../components/Layout'
import PostCard from '../../components/PostCard'
import { getCategories, getPostsByCategory } from '../../lib/ghost'

export default function CategoryPage({ category, posts }) {
  return (
    <Layout>
      <Head>
        <title>{category?.name || 'Category'} - Medium Blog</title>
      </Head>

      <Link href="/categories" className="back-btn">
        ← All Categories
      </Link>

      <section className="hero" style={{ textAlign: 'left', paddingTop: '2rem' }}>
        <h1>{category?.name}</h1>
        {category?.description && (
          <p>{category.description}</p>
        )}
      </section>

      {posts.length > 0 ? (
        <div className="posts-grid">
          {posts.map(post => (
            <PostCard key={post.id} post={post} />
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <h2>No posts in this category</h2>
          <p>Check back later for new content.</p>
        </div>
      )}
    </Layout>
  )
}

export async function getServerSideProps({ params }) {
  const categories = await getCategories()
  const category = categories.find(c => c.slug === params.slug)
  const posts = await getPostsByCategory(params.slug)

  return {
    props: {
      category: category || null,
      posts: posts || []
    }
  }
}
