import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'
import gettextParser from 'gettext-parser'
import { globSync } from 'glob'

const frontendRoot = path.resolve(process.cwd())
const repositoryRoot = path.resolve(frontendRoot, '..')
const localeRoot = path.join(repositoryRoot, 'locales')
const englishRoot = path.join(frontendRoot, 'src', 'i18n', 'locales', 'en')
const sourceFiles = globSync('src/**/*.{ts,tsx}', { cwd: frontendRoot, absolute: true, windowsPathsNoEscape: true, ignore: ['**/*.test.*', '**/*.d.ts', '**/i18n/**'] }).sort()
const allowedExact = new Set(['SKU', 'FlowHub'])
const uiAttributes = new Set(['placeholder', 'title', 'aria-label', 'alt', 'description', 'label', 'emptyText', 'actionLabel', 'helpText', 'caption'])
const uiProperties = new Set(['title', 'description', 'label', 'message', 'summary', 'recommendedAction', 'emptyText', 'actionLabel', 'helpText', 'caption'])

function loadEnglish() {
  const resources = {}
  for (const file of globSync('*.json', { cwd: englishRoot, absolute: true, windowsPathsNoEscape: true }).sort()) {
    const namespace = path.basename(file, '.json')
    if (namespace !== 'manifest') resources[namespace] = JSON.parse(fs.readFileSync(file, 'utf8'))
  }
  return resources
}

function glossaryComment(message) {
  const terms = {
    Apply: 'Apply means executing an approved change against a sales Channel.', Review: 'Review is the immutable validation result required before Apply.', Draft: 'Draft is a saved immutable revision of proposed changes.', Listing: 'Listing means one independently identifiable product record in a sales Channel.', Source: 'Source means the spreadsheet or managed sheet supplying product targets.', Channel: 'Channel means an external sales destination such as WooCommerce.', Mapping: 'Mapping links Source fields and products to Channel Listing identities.', Current: 'Current is the latest verified or cached Channel value.', Target: 'Target is the proposed value that may be applied after Review.', Stock: 'Stock means the sellable inventory value supported by a Channel.', Reconciliation: 'Reconciliation verifies an uncertain external write without blindly redispatching it.',
  }
  return Object.entries(terms).find(([term]) => new RegExp(`\\b${term}\\b`, 'i').test(message))?.[1]
}

function sourceReferences() {
  const references = new Map()
  const pattern = /translate\(\s*['"]([^'"]+)['"]/g
  for (const file of sourceFiles) {
    const source = fs.readFileSync(file, 'utf8')
    let match
    while ((match = pattern.exec(source))) {
      const line = source.slice(0, match.index).split(/\r?\n/).length
      const ref = `${path.relative(repositoryRoot, file).replaceAll('\\', '/')}:${line}`
      const list = references.get(match[1]) ?? []
      if (!list.includes(ref)) list.push(ref)
      references.set(match[1], list)
    }
  }
  return references
}

function catalogEntries() {
  const resources = loadEnglish()
  const refs = sourceReferences()
  const entries = []
  for (const namespace of Object.keys(resources).sort()) {
    const messages = resources[namespace]
    const consumed = new Set()
    for (const key of Object.keys(messages).sort()) {
      if (consumed.has(key)) continue
      if (key.endsWith('_one') && Object.hasOwn(messages, `${key.slice(0, -4)}_other`)) {
        const base = key.slice(0, -4)
        consumed.add(key); consumed.add(`${base}_other`)
        entries.push({ namespace, key: base, message: messages[key], plural: messages[`${base}_other`], references: [...(refs.get(`${namespace}:${base}`) ?? []), ...(refs.get(`${namespace}:${key}`) ?? [])] })
      } else if (!key.endsWith('_other')) entries.push({ namespace, key, message: messages[key], plural: null, references: refs.get(`${namespace}:${key}`) ?? [] })
    }
  }
  return entries
}

function poDocument(language, template = false) {
  const translations = {}
  for (const entry of catalogEntries()) {
    const context = `${entry.namespace}:${entry.key}`
    translations[context] = {
      [entry.message]: {
        msgctxt: context,
        msgid: entry.message,
        ...(entry.plural ? { msgid_plural: entry.plural } : {}),
        msgstr: template ? (entry.plural ? ['', ''] : ['']) : (entry.plural ? [entry.message, entry.plural] : [entry.message]),
        comments: {
          ...(entry.references.length ? { reference: [...new Set(entry.references)].sort().join(' ') } : {}),
          ...(glossaryComment(`${entry.message} ${entry.plural ?? ''}`) ? { extracted: glossaryComment(`${entry.message} ${entry.plural ?? ''}`) } : {}),
        },
      },
    }
  }
  return {
    charset: 'utf-8',
    headers: {
      'project-id-version': 'FlowHub 1.3',
      'content-type': 'text/plain; charset=UTF-8',
      'content-transfer-encoding': '8bit',
      'mime-version': '1.0',
      'language': language,
      'plural-forms': 'nplurals=2; plural=(n != 1);',
      'x-generator': 'FlowHub deterministic i18n extractor',
    },
    translations,
  }
}

function writePo(file, document) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  const output = gettextParser.po.compile(document, { foldLength: 0, sort: true }).toString('utf8').replace(/\r\n/g, '\n')
  fs.writeFileSync(file, output.endsWith('\n') ? output : `${output}\n`)
}

function extract() {
  const entries = catalogEntries()
  writePo(path.join(localeRoot, 'flowhub.pot'), poDocument('en', true))
  writePo(path.join(localeRoot, 'en', 'flowhub.po'), poDocument('en', false))
  const plural = entries.filter(entry => entry.plural).length
  const interpolation = entries.filter(entry => /\{\{[^}]+\}\}/.test(`${entry.message} ${entry.plural ?? ''}`)).length
  console.log(`Extracted ${entries.length} messages across ${new Set(entries.map(entry => entry.namespace)).size} namespaces (${plural} plural, ${interpolation} interpolated).`)
}

function placeholders(value) {
  return [...value.matchAll(/\{\{\s*([^},\s]+)[^}]*\}\}/g)].map(match => match[1]).sort()
}

function samePlaceholders(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index])
}

function catalogValidationErrors(file) {
  const parsed = gettextParser.po.parse(fs.readFileSync(file))
  const errors = []
  const locale = path.basename(path.dirname(file))
  for (const context of Object.values(parsed.translations)) for (const item of Object.values(context)) {
    if (!item.msgid) continue
    const singular = placeholders(item.msgid)
    const plural = placeholders(item.msgid_plural ?? item.msgid)
    const translations = item.msgstr ?? []
    translations.forEach((translation, index) => {
      if (!translation) return
      const expected = index === 0 ? singular : plural
      if (!samePlaceholders(placeholders(translation), expected)) {
        errors.push(`${path.relative(repositoryRoot, file)} ${item.msgctxt ?? item.msgid} form ${index}: placeholder mismatch`)
      }
    })
    if (item.msgid_plural && translations.length > 0 && translations.length < 2) {
      errors.push(`${path.relative(repositoryRoot, file)} ${item.msgctxt ?? item.msgid}: plural entry has fewer than two forms`)
    }
    if (locale === 'en' && translations.some(translation => !translation)) {
      errors.push(`${path.relative(repositoryRoot, file)} ${item.msgctxt ?? item.msgid}: English fallback is incomplete`)
    }
  }
  return errors
}

function hardcodedFindings() {
  const findings = []
  const record = (file, sf, node, value, kind) => {
    const text = value.replace(/\s+/g, ' ').trim()
    if (!/[A-Za-z]{2}/.test(text) || allowedExact.has(text) || /^(https?:|\/api\/|[A-Z0-9_:-]+)$/.test(text) || /^[a-z][A-Za-z0-9]*(?::[A-Za-z0-9_.]+|\.[A-Za-z0-9_.]+)+$/.test(text)) return
    const tokens = text.split(' ')
    if (/^(?:fh-|flex\b|grid\b|bg-|text-|md:|sm:|lg:|xl:)/.test(text) && tokens.every(token => /^[A-Za-z0-9_!:[\]./%-]+$/.test(token))) return
    const line = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1
    const sourceLines = sf.getFullText().split(/\r?\n/)
    if (`${sourceLines[line - 2] ?? ''} ${sourceLines[line - 1] ?? ''}`.includes('i18n-ignore')) return
    findings.push(`${path.relative(repositoryRoot, file).replaceAll('\\', '/')}:${line} ${kind}: ${text}`)
  }
  for (const file of sourceFiles) {
    const source = fs.readFileSync(file, 'utf8')
    const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
    const renderedIdentifiers = new Set()
    function collectRenderedIdentifiers(node) {
      if (ts.isIdentifier(node) && !(ts.isPropertyAccessExpression(node.parent) && node.parent.name === node)) renderedIdentifiers.add(node.text)
      ts.forEachChild(node, collectRenderedIdentifiers)
    }
    function collectRendered(node) {
      if (ts.isJsxExpression(node) && node.expression) {
        const attribute = ts.isJsxAttribute(node.parent) ? node.parent.name.text : null
        if (!attribute || uiAttributes.has(attribute)) collectRenderedIdentifiers(node.expression)
      }
      ts.forEachChild(node, collectRendered)
    }
    collectRendered(sf)
    function isTranslateArgument(node) {
      let current = node.parent
      while (current && !ts.isStatement(current) && !ts.isSourceFile(current)) {
        if (ts.isCallExpression(current) && ts.isIdentifier(current.expression) && current.expression.text === 'translate') return true
        current = current.parent
      }
      return false
    }
    function isRendered(node) {
      let parent = node.parent
      while (parent && !ts.isSourceFile(parent) && !ts.isStatement(parent)) {
        if (ts.isJsxExpression(parent)) return !ts.isJsxAttribute(parent.parent)
        if (ts.isJsxAttribute(parent)) return uiAttributes.has(parent.name.text)
        if (ts.isPropertyAssignment(parent) && (ts.isIdentifier(parent.name) || ts.isStringLiteral(parent.name))) return uiProperties.has(parent.name.text)
        parent = parent.parent
      }
      return false
    }
    function visit(node) {
      if (ts.isJsxText(node)) record(file, sf, node, node.getText(sf), 'JSX text')
      if (ts.isJsxAttribute(node) && uiAttributes.has(node.name.text) && node.initializer && ts.isStringLiteral(node.initializer)) record(file, sf, node, node.initializer.text, `attribute ${node.name.text}`)
      if (ts.isPropertyAssignment(node) && (ts.isIdentifier(node.name) || ts.isStringLiteral(node.name)) && uiProperties.has(node.name.text) && ts.isStringLiteral(node.initializer)) record(file, sf, node, node.initializer.text, `property ${node.name.text}`)
      if (ts.isConditionalExpression(node) && isRendered(node) && ts.isStringLiteral(node.whenTrue)) record(file, sf, node.whenTrue, node.whenTrue.text, 'rendered conditional')
      if (ts.isConditionalExpression(node) && isRendered(node) && ts.isStringLiteral(node.whenFalse)) record(file, sf, node.whenFalse, node.whenFalse.text, 'rendered conditional')
      if (ts.isTemplateExpression(node) && !isTranslateArgument(node)) {
        const literal = [node.head.text, ...node.templateSpans.map(span => span.literal.text)].join(' ')
        let parent = node.parent
        while (parent && !ts.isSourceFile(parent) && !ts.isStatement(parent)) {
          if (ts.isJsxExpression(parent)) {
            if (!ts.isJsxAttribute(parent.parent) || uiAttributes.has(parent.parent.name.text)) record(file, sf, node, literal, 'rendered template')
            break
          }
          if (ts.isPropertyAssignment(parent) && (ts.isIdentifier(parent.name) || ts.isStringLiteral(parent.name)) && uiProperties.has(parent.name.text)) { record(file, sf, node, literal, 'rendered template'); break }
          parent = parent.parent
        }
      }
      if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && renderedIdentifiers.has(node.name.text) && node.initializer) {
        function inspectInitializer(value) {
          if (ts.isStringLiteral(value) && /[A-Za-z]{2}[^\n]*\s+[A-Za-z]{2}/.test(value.text)) record(file, sf, value, value.text, `rendered constant ${node.name.text}`)
          ts.forEachChild(value, inspectInitializer)
        }
        inspectInitializer(node.initializer)
      }
      if (ts.isFunctionDeclaration(node) && node.name && renderedIdentifiers.has(node.name.text) && node.body && (!node.type || node.type.kind === ts.SyntaxKind.StringKeyword)) {
        function inspectRenderedFunction(value) {
          if (ts.isReturnStatement(value) && value.expression && !isTranslateArgument(value.expression)) {
            if (ts.isStringLiteral(value.expression)) record(file, sf, value.expression, value.expression.text, `rendered function ${node.name.text}`)
            if (ts.isTemplateExpression(value.expression)) {
              const literal = [value.expression.head.text, ...value.expression.templateSpans.map(span => span.literal.text)].join(' ')
              record(file, sf, value.expression, literal, `rendered function ${node.name.text}`)
            }
          }
          ts.forEachChild(value, inspectRenderedFunction)
        }
        inspectRenderedFunction(node.body)
      }
      if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && /^(?:notify|notifyError|notifySuccess|toast|alert)$/.test(node.expression.text)) {
        const first = node.arguments[0]
        if (first && ts.isStringLiteral(first)) record(file, sf, first, first.text, `notification ${node.expression.text}`)
      }
      ts.forEachChild(node, visit)
    }
    visit(sf)
  }
  return findings
}

function validate() {
  const resources = loadEnglish()
  const missing = []
  for (const [key, refs] of sourceReferences()) {
    const [namespace, ...parts] = key.split(':')
    const resourceKey = parts.join(':')
    if (!resources[namespace] || (!Object.hasOwn(resources[namespace], resourceKey) && !Object.hasOwn(resources[namespace], `${resourceKey}_one`))) missing.push(`${key} (${refs.join(', ')})`)
  }
  const potFile = path.join(localeRoot, 'flowhub.pot')
  if (!fs.existsSync(potFile)) throw new Error('locales/flowhub.pot is missing; run npm run i18n:extract.')
  gettextParser.po.parse(fs.readFileSync(potFile))
  const placeholderErrors = globSync('*/flowhub.po', { cwd: localeRoot, absolute: true, windowsPathsNoEscape: true })
    .sort()
    .flatMap(catalogValidationErrors)
  const hardcoded = hardcodedFindings()
  if (missing.length || placeholderErrors.length || hardcoded.length) {
    if (missing.length) console.error(`Missing keys:\n${missing.join('\n')}`)
    if (placeholderErrors.length) console.error(`Catalog errors:\n${placeholderErrors.join('\n')}`)
    if (hardcoded.length) console.error(`Hardcoded user-facing strings:\n${hardcoded.join('\n')}`)
    process.exitCode = 1
    return
  }
  console.log(`Validated ${catalogEntries().length} messages; 0 missing keys, 0 placeholder mismatches, 0 unapproved hardcoded strings.`)
}

function compile() {
  const files = globSync('*/flowhub.po', { cwd: localeRoot, absolute: true, windowsPathsNoEscape: true }).sort()
  for (const file of files) {
    const catalogErrors = catalogValidationErrors(file)
    if (catalogErrors.length) throw new Error(`Invalid translation catalog:\n${catalogErrors.join('\n')}`)
    const locale = path.basename(path.dirname(file))
    const parsed = gettextParser.po.parse(fs.readFileSync(file))
    const output = {}
    let translated = 0
    let total = 0
    for (const context of Object.values(parsed.translations)) for (const item of Object.values(context)) {
      if (!item.msgctxt || !item.msgid) continue
      total += 1
      const separator = item.msgctxt.indexOf(':')
      if (separator < 1) continue
      const namespace = item.msgctxt.slice(0, separator)
      const key = item.msgctxt.slice(separator + 1)
      output[namespace] ??= {}
      if (item.msgid_plural) {
        if (item.msgstr[0]?.trim() && item.msgstr[1]?.trim()) translated += 1
        output[namespace][`${key}_one`] = item.msgstr[0] || item.msgid
        output[namespace][`${key}_other`] = item.msgstr[1] || item.msgid_plural
      } else {
        if (item.msgstr[0]?.trim()) translated += 1
        output[namespace][key] = item.msgstr[0] || item.msgid
      }
    }
    const target = path.join(frontendRoot, 'src', 'i18n', 'locales', locale)
    fs.mkdirSync(target, { recursive: true })
    for (const [namespace, values] of Object.entries(output)) fs.writeFileSync(path.join(target, `${namespace}.json`), `${JSON.stringify(Object.fromEntries(Object.entries(values).sort(([a], [b]) => a.localeCompare(b))), null, 2)}\n`)
    fs.writeFileSync(path.join(target, 'manifest.json'), `${JSON.stringify({ locale, complete: total > 0 && translated === total, translated, total }, null, 2)}\n`)
    console.log(`Compiled ${file} into ${Object.keys(output).length} runtime namespaces (${translated}/${total} translated).`)
  }
}

const command = process.argv[2]
if (command === 'extract') extract()
else if (command === 'validate') validate()
else if (command === 'compile') compile()
else throw new Error('Use: node scripts/i18n.mjs extract|validate|compile')
