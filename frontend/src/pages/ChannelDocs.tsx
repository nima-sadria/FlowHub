import { useMemo, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router'
import Badge from '../components/Badge'
import BrandIcon from '../components/BrandIcon'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import { translate } from '../i18n'
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
  comingSoon?: boolean
}

type DocumentSection = {
  id: string
  title: string
  content: string
}

function channelDocuments(): ChannelDocument[] {
  return [
    {
      id: 'snappshop',
      title: translate('commerce:commerceHub.channelDocs.snappshop.title'),
      provider: 'SnappShop',
      description: translate('commerce:commerceHub.channelDocs.snappshop.description'),
      protocol: translate('commerce:commerceHub.channelDocs.snappshop.protocol'),
      markdown: snappshopMarkdown,
    },
    {
      id: 'tapsishop',
      title: translate('commerce:commerceHub.channelDocs.tapsishop.title'),
      provider: 'TapsiShop',
      description: translate('commerce:commerceHub.channelDocs.tapsishop.description'),
      protocol: translate('commerce:commerceHub.channelDocs.tapsishop.protocol'),
      markdown: tapsishopMarkdown,
    },
    {
      id: 'technolife',
      title: translate('commerce:commerceHub.channelDocs.technolife.title'),
      provider: 'Technolife',
      description: translate('commerce:commerceHub.channelDocs.technolife.description'),
      protocol: translate('commerce:commerceHub.channelDocs.technolife.protocol'),
      markdown: technolifeMarkdown,
    },
    {
      id: 'woocommerce',
      title: translate('commerce:commerceHub.channelDocs.woocommerce.title'),
      provider: 'WooCommerce',
      description: translate('commerce:commerceHub.channelDocs.woocommerce.description'),
      protocol: translate('commerce:commerceHub.channelDocs.woocommerce.protocol'),
      markdown: woocommerceMarkdown,
    },
    {
      id: 'digikala',
      title: translate('commerce:commerceHub.channelDocs.digikala.title'),
      provider: 'Digikala',
      description: translate('commerce:commerceHub.channelDocs.digikala.description'),
      protocol: translate('commerce:commerceHub.channelDocs.digikala.protocol'),
      markdown: digikalaMarkdown,
      comingSoon: true,
    },
  ]
}

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
            <Icon name="copy" /> {copiedBlock === codeId
              ? translate('commerce:commerceHub.channelDocs.copied')
              : translate('commerce:commerceHub.channelDocs.copy')}
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
  const documents = channelDocuments()
  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('commerce:commerceHub.channelDocs.indexTitle')}</h1>
          <p className="fh-page-subtitle">{translate('commerce:commerceHub.channelDocs.indexSubtitle')}</p>
        </div>
      </div>
      <section className="fh-docs-grid" aria-label={translate('commerce:commerceHub.channelDocs.indexAriaLabel')}>
        {documents.map(document => (
          <article className="fh-card fh-card-pad fh-docs-card" data-testid={`channel-docs-${document.id}`} key={document.id}>
            <div className="fh-docs-card-topline">
              <div className="flex items-center gap-2">
                <BrandIcon identity={{ provider: document.id }} label={document.provider} size={36} />
                <span className="fh-docs-provider">{document.provider}</span>
              </div>
              {document.comingSoon ? (
                <Badge variant="neutral">{translate('common:resourceBadge.comingSoon')}</Badge>
              ) : (
                <span className="fh-docs-status">{translate('commerce:commerceHub.channelDocs.documentationAvailable')}</span>
              )}
            </div>
            <h2 className="fh-section-title mt-4">{document.title}</h2>
            <p className="fh-section-subtitle mt-2">{document.description}</p>
            {document.comingSoon && (
              <p className="fh-alert-warning mt-3" data-testid={`channel-docs-coming-soon-disclaimer-${document.id}`} role="note">
                {translate('commerce:commerceHub.channelDocs.digikala.disclaimer')}
              </p>
            )}
            <p className="fh-docs-protocol" dir="ltr">{document.protocol}</p>
            <button className="fh-button-secondary mt-5" type="button" onClick={() => navigate(`/docs/channels/${document.id}`)}>
              <Icon name="file" /> {translate('commerce:commerceHub.channelDocs.viewDocumentation')}
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
  const channelDocument = channelDocuments().find(item => item.id === channelId)
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
            <Icon name="previous" mirrorRtl /> {translate('commerce:commerceHub.channelDocs.backToDocuments')}
          </button>
          <div className="mt-2 flex items-center gap-3">
            <BrandIcon identity={{ provider: channelDocument.id }} label={channelDocument.provider} size={36} />
            <h1 className="fh-page-title">{channelDocument.title}</h1>
            {channelDocument.comingSoon && <Badge variant="neutral">{translate('common:resourceBadge.comingSoon')}</Badge>}
          </div>
          <p className="fh-page-subtitle">{channelDocument.description}</p>
          {channelDocument.comingSoon && (
            <p className="fh-alert-warning mt-3" data-testid="channel-docs-coming-soon-disclaimer" role="note">
              {translate('commerce:commerceHub.channelDocs.digikala.disclaimer')}
            </p>
          )}
        </div>
        <span className="fh-docs-protocol fh-docs-protocol-header" dir="ltr">{channelDocument.protocol}</span>
      </div>

      <div className="fh-docs-search">
        <Icon name="search" size="sm" className="fh-docs-search-icon" />
        <input
          type="search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder={translate('commerce:commerceHub.channelDocs.searchPlaceholder')}
          aria-label={translate('commerce:commerceHub.channelDocs.searchPlaceholder')}
        />
        {query && <button className="fh-docs-search-clear" type="button" onClick={() => setQuery('')} aria-label={translate('commerce:commerceHub.channelDocs.clearSearch')}><Icon name="close" /></button>}
      </div>

      <div className="fh-docs-layout">
        <aside className="fh-docs-toc" aria-label={translate('commerce:commerceHub.channelDocs.tableOfContents')}>
          <p className="fh-docs-toc-label">{translate('commerce:commerceHub.channelDocs.tableOfContents')}</p>
          {visibleSections.map(section => <button key={section.id} type="button" onClick={() => window.document.getElementById(section.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{section.title}</button>)}
        </aside>
        <article className="fh-card fh-card-pad fh-docs-document">
          {visibleSections.length === 0 ? (
            <div className="fh-docs-empty"><Icon name="search" size="md" /><p>{translate('commerce:commerceHub.channelDocs.noSearchResults')}</p></div>
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
