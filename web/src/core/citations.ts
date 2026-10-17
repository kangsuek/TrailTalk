// 일지 인용(S3-23) 표시 도우미. UI·브라우저 API에 의존하지 않는다(안드로이드 포팅 대상).

/** 출처 번호 표시: [1][2] */
export function citeLabel(cites: readonly number[]): string {
  return cites.map((n) => `[${n}]`).join('')
}

/** 링크로 열어도 되는 주소인가(http·https만. 서버가 저장할 때도 거르지만 그릴 때 한 번 더 막는다) */
export function isWebUrl(url: string): boolean {
  return /^https?:\/\//i.test(url)
}
