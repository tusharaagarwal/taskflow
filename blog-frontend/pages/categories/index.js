import Head from 'next/head'
import Link from 'next/link'
import Layout from '../../components/Layout'
import { getCategories, getPosts } from '../../lib/ghost'

export default function CategoriesPage({ categories, postsByCategory }) {
  return (
    <Layout>
      <Head>
        <title>Categories - Medium Blog</title>
      </Head>

      <section className="hero">
        <h1>Categories</h1>
        <p>Browse posts by topic</p>
      </section>

      <div style={{ marginTop: '2rem' }}>
        {categories.map(category => (
          <div key={category.id} style={{ marginBottom: '2rem' }}>
            <Link href={`/categories/${category.slug}`}>
              <h2 style={{ 
                fontFamily: 'var(--font-serif)', 
                fontSize: '1.5rem',
                marginBottom: '1rem',
                color: 'var(--color-primary)'
              }}>
                {category.name}
                <span style={{ color: 'var(--color-secondary)', fontSize: '1rem', marginLeft: '0.5rem' }}>
                  ({postsByCategory[category.slug]?.length || 0} posts)
                </span>
              </h2>
            </Link>
            <p style={{ color: 'var(--color-secondary)', marginBottom: '1rem' }}>
              {category.description || `Explore all ${category.name} posts`}
            </p>
          </div>
        ))}
      </div>
    </Layout>
  )
}

export async function getServerSideProps() {
  const categories = await getCategories()
  const allPosts = await getPosts()
  
  const postsByCategory = {}
  allPosts.forEach(post => {
    if (post.primary_category) {
      const slug = post.primary_category.slug
      if (!postsByCategory[slug]) {
        postsByCategory[slug] = []
      }
      postsByCategory[slug].push(post)
    }
  })

  return {
    props: {
      categories: categories || [],
      postsByCategory
    }
  }
}
