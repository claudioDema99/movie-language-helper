import { readFileSync } from 'node:fs'

const lockfileUrl = new URL('../package-lock.json', import.meta.url)
const lockfile = JSON.parse(readFileSync(lockfileUrl, 'utf8'))
const packages = Object.entries(lockfile.packages)
  .filter(([path]) => path.includes('node_modules/'))
  .map(([path, metadata]) => {
    const name = path.slice(path.lastIndexOf('node_modules/') + 13)
    return `${name}@${metadata.version} | ${metadata.license ?? 'UNKNOWN'}`
  })
  .sort((left, right) => left.localeCompare(right))

for (const packageLicense of packages) {
  console.log(packageLicense)
}

