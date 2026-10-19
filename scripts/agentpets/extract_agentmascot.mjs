import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../../plugins.v3/agentpets/frontend/package.json', import.meta.url))
const ts = require('typescript')
const { unzipSync, strFromU8 } = require('fflate')
const [archive, output] = process.argv.slice(2)
if (!archive || !output) throw new Error('Usage: node extract_agentmascot.mjs archive.zip output.json')
const zip = unzipSync(readFileSync(archive))
const candidates = Object.keys(zip).filter(name => /^agentmascot\/dist\/assets\/runtime-[^/]+\.js$/.test(name))
if (candidates.length !== 1) throw new Error('Expected exactly one AgentMascot runtime')
const source = ts.createSourceFile(candidates[0], strFromU8(zip[candidates[0]]), ts.ScriptTarget.Latest, true)
const declarations = new Map()
for (const statement of source.statements) {
  if (!ts.isVariableStatement(statement)) continue
  for (const declaration of statement.declarationList.declarations)
    if (ts.isIdentifier(declaration.name)) declarations.set(declaration.name.text, declaration.initializer)
}
const cache = new Map()
const assets = {}
const pending = new Set()

function value(name) {
  if (cache.has(name)) return cache.get(name)
  if (pending.has(name) || !declarations.has(name)) throw new Error(`Invalid constant reference: ${name}`)
  pending.add(name)
  const node = declarations.get(name)
  let result
  if (ts.isStringLiteral(node) && node.text.startsWith('data:image/png;base64,')) {
    assets[name] = node.text.slice('data:image/png;base64,'.length)
    result = { image: name }
  } else result = literal(node)
  cache.set(name, result)
  pending.delete(name)
  return result
}

// Interpret only data literals and the documented pose constructor; never execute archive code.
function literal(node) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text
  if (ts.isNumericLiteral(node)) return Number(node.text)
  if (node.kind === ts.SyntaxKind.TrueKeyword) return true
  if (node.kind === ts.SyntaxKind.FalseKeyword) return false
  if (ts.isIdentifier(node)) return value(node.text)
  if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.MinusToken) return -literal(node.operand)
  if (ts.isArrayLiteralExpression(node)) return node.elements.flatMap(item => ts.isSpreadElement(item) ? literal(item.expression) : [literal(item)])
  if (ts.isPropertyAccessExpression(node)) {
    const object = literal(node.expression)
    if (!Object.hasOwn(object, node.name.text)) throw new Error(`Missing data property: ${node.name.text}`)
    return object[node.name.text]
  }
  if (ts.isObjectLiteralExpression(node)) {
    const result = Object.create(null)
    for (const property of node.properties) {
      if (ts.isSpreadAssignment(property)) Object.assign(result, literal(property.expression))
      else if (ts.isShorthandPropertyAssignment(property)) result[property.name.text] = value(property.name.text)
      else if (ts.isPropertyAssignment(property)) result[property.name.text] = literal(property.initializer)
      else throw new Error('Unsupported object member')
    }
    return result
  }
  if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'pose') {
    const [imageName, anchor = value('GROUND_FOOT_ANCHOR'), velocity = [0, 0], duration = 250] = node.arguments.map(literal)
    return { imageName, anchor, velocity, duration }
  }
  throw new Error(`Unsupported data expression: ${ts.SyntaxKind[node.kind]}`)
}

const baseActions = value('SHIMEJI_ACTIONS')
const overrides = value('MASCOT_ACTION_OVERRIDES')
const profiles = value('MASCOT_PROFILES')
const aliases = value('SEMANTIC_ACTION_ALIASES')
// Preserve unused original frames as well as all frames referenced by native actions.
for (const [name, node] of declarations)
  if (ts.isStringLiteral(node) && node.text.startsWith('data:image/png;base64,')) value(name)
const result = {
  tick_ms: value('SHIMEJI_TICK_MS'),
  runtime_entry: candidates[0],
  anchors: { ground: value('GROUND_FOOT_ANCHOR'), air: value('GROUND_FOOT_ANCHOR'), wall: value('WALL_GRAB_ANCHOR'), ceiling: value('CEILING_GRAB_ANCHOR') },
  profiles: Object.fromEntries(Object.entries(profiles).map(([key, profile]) => [key, {
    label: profile.label,
    images: Object.fromEntries(Object.entries(profile.images).map(([name, image]) => [name, image.image])),
    actions: { ...baseActions, ...overrides[key] },
  }])),
  aliases,
  assets,
}
writeFileSync(output, JSON.stringify(result))
console.log(JSON.stringify({ profiles: Object.keys(profiles), images: Object.keys(assets).length, tick_ms: result.tick_ms }))
