import { useMemo, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import snappshopMarkdown from '../../../docs/api/channel/snappshop-api-doc.md?raw'
import tapsishopMarkdown from '../../../docs/api/channel/tapsishop-api-doc.md?raw'
import technolifeMarkdown from '../../../docs/api/channel/technolife-api.md?raw'
import woocommerceMarkdown from '../../../docs/api/channel/woocommerce-api.md?raw'
import digikalaMarkdown from '../../../docs/api/channel/digikala-api.md?raw'

type ChannelDocument = {
  id: string
  title: string
  provider: string
  description: string
  protocol: string
  markdown: string
}

type DocumentSection = {
  id: string
  title: string
  content: string
}

const channelDocuments: ChannelDocument[] = [
  {
    id: 'snappshop',
    title: 'API اسنپ‌شاپ',
    provider: 'SnappShop',
    description: 'مدیریت فروشگاه‌ها، محصولات، قیمت و موجودی و سفارشات.',
    protocol: 'REST · JSON · Bearer Token',
    markdown: snappshopMarkdown,
  },
  {
    id: 'tapsishop',
    title: 'API تپسی‌شاپ',
    provider: 'TapsiShop',
    description: 'وب‌هوک سفارش، تحویل سفارش و به‌روزرسانی قیمت و موجودی.',
    protocol: 'REST · JSON · Token Header',
    markdown: tapsishopMarkdown,
  },
  {
    id: 'technolife',
    title: 'API تکنولایف',
    provider: 'Technolife',
    description: 'مدیریت محصول، تنوع، قیمت‌گذاری، تخفیف و سفارشات SBS.',
    protocol: 'REST · JSON · Bearer + encrypted-secret',
    markdown: technolifeMarkdown,
  },
  {
    id: 'woocommerce',
    title: 'API ووکامرس',
    provider: 'WooCommerce',
    description: 'مدیریت داده‌های فروشگاه، سفارش‌ها، محصولات و وب‌هوک‌های API v3.',
    protocol: 'REST · JSON · Basic Auth / OAuth 1.0a',
    markdown: woocommerceMarkdown,
  },
  {
    id: 'digikala',
    title: 'API دیجی‌کالا',
    provider: 'Digikala',
    description: 'مدیریت کالا، تنوع، موجودی، سفارش، بسته و وب‌هوک‌های فروشندگان.',
    protocol: 'REST · JSON · JWT Bearer Token',
    markdown: digikalaMarkdown,
  },
]

function sectionsFromMarkdown(markdown: string): DocumentSection[] {
  const body = markdown.replace(/^#\s+.+\n+/, '')
  const firstSection = body.search(/^##\s+/m)
  const fragments = (firstSection >= 0 ? body.slice(firstSection) : body).split(/(?=^##\s+)/m).filter(Boolean)
  return fragments.map((fragment, index) => {
    const [heading, ...rest] = fragment.split('\n')
    return {
      id: `section-${index + 1}`,
      title: heading.replace(/^##\s+/, ''),
      content: rest.join('\n').trim(),
    }
  })
}

function inlineMarkdown(value: string): ReactNode[] {
  return value.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>
    return part
  })
}

function MarkdownContent({ content }: { content: string }) {
  const [copiedBlock, setCopiedBlock] = useState<number | null>(null)
  const lines = content.split('\n')
  const blocks: ReactNode[] = []
  let index = 0
  let blockIndex = 0

  async function copyCode(code: string, id: number) {
    try {
      await navigator.clipboard?.writeText(code)
      setCopiedBlock(id)
      window.setTimeout(() => setCopiedBlock(current => current === id ? null : current), 1600)
    } catch {
      setCopiedBlock(null)
    }
  }

  while (index < lines.length) {
    const line = lines[index]
    if (!line.trim()) {
      index += 1
      continue
    }

    if (line.startsWith('```')) {
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !lines[index].startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }
      index += 1
      const code = codeLines.join('\n')
      const codeId = blockIndex++
      blocks.push(
        <div className="fh-docs-code" key={`code-${codeId}`} dir="ltr">
          <button className="fh-docs-copy" type="button" onClick={() => void copyCode(code, codeId)}>
            <Icon name="copy" /> {copiedBlock === codeId ? 'کپی شد' : 'کپی'}
          </button>
          <pre><code>{code}</code></pre>
        </div>,
      )
      continue
    }

    const heading = line.match(/^(#{3,6})\s+(.+)$/)
    if (heading) {
      const level = heading[1].length
      const text = heading[2]
      const className = level === 3 ? 'fh-docs-heading' : 'fh-docs-subheading'
      blocks.push(level === 3
        ? <h3 className={className} key={`heading-${index}`}>{inlineMarkdown(text)}</h3>
        : <h4 className={className} key={`heading-${index}`}>{inlineMarkdown(text)}</h4>)
      index += 1
      continue
    }

    if (line.startsWith('|')) {
      const tableLines: string[] = []
      while (index < lines.length && lines[index].startsWith('|')) {
        tableLines.push(lines[index])
        index += 1
      }
      const rows = tableLines
        .filter((_, rowIndex) => rowIndex !== 1)
        .map(row => row.slice(1, -1).split('|').map(cell => cell.trim().replace(/\\\|/g, '|')))
      if (rows.length > 0) {
        const [header, ...body] = rows
        blocks.push(
          <div className="fh-docs-table-wrap" key={`table-${blockIndex++}`}>
            <table className="fh-docs-table">
              <thead><tr>{header.map((cell, cellIndex) => <th key={cellIndex}>{inlineMarkdown(cell)}</th>)}</tr></thead>
              <tbody>{body.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{inlineMarkdown(cell)}</td>)}</tr>)}</tbody>
            </table>
          </div>,
        )
      }
      continue
    }

    if (line.startsWith('- ')) {
      const items: string[] = []
      while (index < lines.length && lines[index].startsWith('- ')) {
        items.push(lines[index].slice(2))
        index += 1
      }
      blocks.push(<ul className="fh-docs-list" key={`list-${blockIndex++}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item)}</li>)}</ul>)
      continue
    }

    if (line.startsWith('> ')) {
      blocks.push(<blockquote className="fh-docs-note" key={`note-${blockIndex++}`}>{inlineMarkdown(line.slice(2))}</blockquote>)
      index += 1
      continue
    }

    const paragraph: string[] = [line]
    index += 1
    while (index < lines.length && lines[index].trim() && !/^(#{3,6}\s+|```|\||- |> )/.test(lines[index])) {
      paragraph.push(lines[index])
      index += 1
    }
    blocks.push(<p className="fh-docs-paragraph" key={`paragraph-${blockIndex++}`}>{inlineMarkdown(paragraph.join(' '))}</p>)
  }

  return <>{blocks}</>
}

function DocsIndex() {
  const navigate = useNavigate()
  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">مستندات API کانال‌ها</h1>
          <p className="fh-page-subtitle">راهنمای اتصال و مدیریت یکپارچه‌سازی کانال‌های فروش در FlowHub.</p>
        </div>
      </div>
      <section className="fh-docs-grid" aria-label="مستندات کانال‌ها">
        {channelDocuments.map(document => (
          <article className="fh-card fh-card-pad fh-docs-card" key={document.id}>
            <div className="fh-docs-card-topline">
              <span className="fh-docs-provider">{document.provider}</span>
              <span className="fh-docs-status">آماده استفاده</span>
            </div>
            <h2 className="fh-section-title mt-4">{document.title}</h2>
            <p className="fh-section-subtitle mt-2">{document.description}</p>
            <p className="fh-docs-protocol" dir="ltr">{document.protocol}</p>
            <button className="fh-button-secondary mt-5" type="button" onClick={() => navigate(`/docs/channels/${document.id}`)}>
              <Icon name="file" /> مشاهده مستندات
            </button>
          </article>
        ))}
      </section>
    </PageShell>
  )
}

export default function ChannelDocs() {
  const { channelId } = useParams()
  const navigate = useNavigate()
  const channelDocument = channelDocuments.find(item => item.id === channelId)
  const [query, setQuery] = useState('')

  const sections = useMemo(() => channelDocument ? sectionsFromMarkdown(channelDocument.markdown) : [], [channelDocument])
  const visibleSections = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    if (!normalizedQuery) return sections
    return sections.filter(section => `${section.title} ${section.content}`.toLocaleLowerCase().includes(normalizedQuery))
  }, [query, sections])

  if (!channelId) return <DocsIndex />
  if (!channelDocument) return <DocsIndex />

  return (
    <PageShell>
      <div className="fh-page-header fh-docs-header">
        <div>
          <button className="fh-docs-back" type="button" onClick={() => navigate('/docs/channels')}>
            <Icon name="previous" mirrorRtl /> همهٔ مستندات
          </button>
          <h1 className="fh-page-title mt-2">{channelDocument.title}</h1>
          <p className="fh-page-subtitle">{channelDocument.description}</p>
        </div>
        <span className="fh-docs-protocol fh-docs-protocol-header" dir="ltr">{channelDocument.protocol}</span>
      </div>

      <div className="fh-docs-search">
        <Icon name="search" size="sm" className="fh-docs-search-icon" />
        <input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="جست‌وجو در مستندات" aria-label="جست‌وجو در مستندات" />
        {query && <button className="fh-docs-search-clear" type="button" onClick={() => setQuery('')} aria-label="پاک کردن جست‌وجو"><Icon name="close" /></button>}
      </div>

      <div className="fh-docs-layout">
        <aside className="fh-docs-toc" aria-label="فهرست بخش‌ها">
          <p className="fh-docs-toc-label">فهرست محتوا</p>
          {visibleSections.map(section => <button key={section.id} type="button" onClick={() => window.document.getElementById(section.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{section.title}</button>)}
        </aside>
        <article className="fh-card fh-card-pad fh-docs-document">
          {visibleSections.length === 0 ? (
            <div className="fh-docs-empty"><Icon name="search" size="md" /><p>بخشی مطابق با جست‌وجوی شما پیدا نشد.</p></div>
          ) : visibleSections.map(section => (
            <section className="fh-docs-section" id={section.id} key={section.id}>
              <h2 className="fh-section-title">{section.title}</h2>
              <MarkdownContent content={section.content} />
            </section>
          ))}
        </article>
      </div>
    </PageShell>
  )
}
