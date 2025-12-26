/** Asks the image CDN for a photo at the size it is shown, instead of the full upload. */
export function photo(url: string, width: number, height = width): string {
  if (!url.includes('images.unsplash.com')) return url
  const sized = new URL(url)
  sized.searchParams.set('w', String(width * 2))
  sized.searchParams.set('h', String(height * 2))
  sized.searchParams.set('fit', 'crop')
  return sized.toString()
}
