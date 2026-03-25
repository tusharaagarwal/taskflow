import Head from 'next/head'
import Link from 'next/link'
import Layout from '../../components/Layout'
import { getPost, getPosts } from '../../lib/ghost'

export default function PostPage({ post }) {
  if (!post) {
    return (
      <Layout>
        <div className="empty-state">
          <h2>Post not found</h2>
          <p>The post you're looking for doesn't exist.</p>
          <Link href="/">← Back to Home</Link>
        </div>
      </Layout>
    )
  }

  const formatDate = (date) => {
    return new Date(date).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  }

  return (
    <Layout>
      <Head>
        <title>{post.title} - Medium Blog</title>
        <meta name="description" content={post.custom_excerpt || post.excerpt} />
        {post.og_image && <meta property="og:image" content={post.og_image} />}
      </Head>

      <article className="single-post">
        <Link href="/" className="back-btn">
          ← Back to Home
        </Link>

        <header className="single-post-header">
          <h1 className="single-post-title">{post.title}</h1>
          <div className="single-post-meta">
            {post.primary_author && (
              <span>By {post.primary_author.name}</span>
            )}
            <span>{formatDate(post.published_at)}</span>
            {post.primary_category && (
              <span>in {post.primary_category.name}</span>
            )}
          </div>
        </header>

        {post.featured_image && (
          <img 
            src={post.featured_image} 
            alt={post.title}
            style={{ width: '100%', height: 'auto', marginBottom: '2rem', borderRadius: '4px' }}
          />
        )}

        <div 
          className="single-post-content"
          dangerouslySetInnerHTML={{ __html: post.html }}
        />

        {post.tags && post.tags.length > 0 && (
          <div className="post-tags" style={{ marginTop: '2rem' }}>
            {post.tags.map(tag => (
              <Link key={tag.id} href={`/tags/${tag.slug}`}>
                <span className="tag">{tag.name}</span>
              </Link>
            ))}
          </div>
        )}

        {post.primary_author && (
          <div className="author-info">
            {post.primary_author.profile_image && (
              <img 
                src={post.primary_author.profile_image} 
                alt={post.primary_author.name}
                style={{ width: '60px', height: '60px', borderRadius: '50%', objectFit: 'cover' }}
              />
            )}
            <div>
              <div className="author-name">{post.primary_author.name}</div>
              <div className="author-bio">{post.primary_author.bio || 'Writer at Medium Blog'}</div>
            </div>
          </div>
        )}
      </article>
    </Layout>
  )
}

export async function getServerSideProps({ params }) {
  const post = await getPost(params.slug)

  return {
    props: {
      post: post || null
    }
  }
}
