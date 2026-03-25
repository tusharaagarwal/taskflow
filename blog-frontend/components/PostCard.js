import Link from 'next/link'
import Image from 'next/image'

export default function PostCard({ post }) {
  const formatDate = (date) => {
    return new Date(date).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    })
  }

  return (
    <article className="post-card">
      {post.featured_image && (
        <div style={{ position: 'relative', width: '100%', height: '200px', marginBottom: '1rem' }}>
          <Image
            src={post.featured_image}
            alt={post.title}
            fill
            style={{ objectFit: 'cover', borderRadius: '4px' }}
            unoptimized
          />
        </div>
      )}
      <div className="post-meta">
        {post.primary_category && (
          <span className="post-category">{post.primary_category.name}</span>
        )}
        <span className="post-date">{formatDate(post.published_at)}</span>
        {post.authors && post.authors[0] && (
          <span>• {post.authors[0].name}</span>
        )}
      </div>
      <h2 className="post-title">
        <Link href={`/post/${post.slug}`}>{post.title}</Link>
      </h2>
      <p className="post-excerpt">{post.custom_excerpt || post.excerpt}</p>
      {post.tags && post.tags.length > 0 && (
        <div className="post-tags">
          {post.tags.slice(0, 3).map(tag => (
            <span key={tag.id} className="tag">{tag.name}</span>
          ))}
        </div>
      )}
    </article>
  )
}

