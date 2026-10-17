// 일지 보고서(S3-22) 표시 도우미. UI·브라우저 API에 의존하지 않는다(안드로이드 포팅 대상).

export interface TextSegment {
  text: string
  bold: boolean
}

/** 서버가 핵심 수치·명칭을 **굵게**로 감싸 보낸다. 짝이 맞는 것만 굵게 하고 나머지 별표는 글자로 둔다 */
export function boldSegments(text: string): TextSegment[] {
  const segments: TextSegment[] = []
  const pattern = /\*\*(.+?)\*\*/g
  let last = 0
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0
    if (start > last) segments.push({ text: text.slice(last, start), bold: false })
    segments.push({ text: match[1], bold: true })
    last = start + match[0].length
  }
  if (last < text.length) segments.push({ text: text.slice(last), bold: false })
  return segments
}

/** 출처 번호 표시: [1][2] */
export function citeLabel(cites: number[]): string {
  return cites.map((n) => `[${n}]`).join('')
}

/** 검색어로 웹 검색하는 주소 */
export function searchUrl(term: string): string {
  return `https://www.google.com/search?q=${encodeURIComponent(term)}`
}

/** 링크로 열어도 되는 주소인가(http·https만. 저장할 때도 거르지만 그릴 때 한 번 더 막는다) */
export function isWebUrl(url: string): boolean {
  return /^https?:\/\//i.test(url)
}
