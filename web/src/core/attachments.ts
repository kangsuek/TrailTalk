// 파일 첨부(FR-22) 보내기 전 검사. 한도의 정본은 서버이고(/api/profile의 client.attachments),
// 여기서는 안내용으로만 검사한다. File 객체에 기대지 않는다(UI·브라우저 API 비의존).

export interface AttachmentLimits {
  max_files: number
  image_upload_max_bytes: number
  text_max_bytes: number
  text_max_chars: number
  max_pdfs: number
  pdf_max_bytes: number
  pdf_max_pages: number
  image_extensions: string[]
  text_extensions: string[]
  pdf_extensions: string[]
}

/** 프로필을 받기 전 대체값(서버 기본값과 같다) */
export const DEFAULT_ATTACHMENT_LIMITS: AttachmentLimits = {
  max_files: 3,
  image_upload_max_bytes: 5 * 1024 * 1024,
  text_max_bytes: 200 * 1024,
  text_max_chars: 10_000,
  max_pdfs: 1,
  pdf_max_bytes: 5 * 1024 * 1024,
  pdf_max_pages: 10,
  image_extensions: ['gif', 'jpeg', 'jpg', 'png', 'webp'],
  text_extensions: ['csv', 'json', 'md', 'txt'],
  pdf_extensions: ['pdf'],
}

export interface FileInfo {
  name: string
  size: number
}

export type AttachmentKind = 'image' | 'text' | 'pdf'

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot < 0 ? '' : name.slice(dot + 1).toLowerCase()
}

export function attachmentKind(name: string, limits: AttachmentLimits): AttachmentKind | null {
  const ext = extensionOf(name)
  if (limits.image_extensions.includes(ext)) return 'image'
  if (limits.text_extensions.includes(ext)) return 'text'
  if (limits.pdf_extensions.includes(ext)) return 'pdf'
  return null
}

function megabytes(bytes: number): string {
  return `${Math.floor(bytes / (1024 * 1024))}MB`
}

/** 붙인 파일 전체(existing + incoming)를 검사해 첫 문제를 한글 안내로 돌려준다. 괜찮으면 null. */
export function checkAttachments(files: FileInfo[], limits: AttachmentLimits): string | null {
  if (files.length > limits.max_files) {
    return `파일은 한 번에 ${limits.max_files}개까지 보낼 수 있어요.`
  }
  if (files.filter((f) => attachmentKind(f.name, limits) === 'pdf').length > limits.max_pdfs) {
    return `PDF는 한 번에 ${limits.max_pdfs}개까지 보낼 수 있어요.`
  }
  for (const file of files) {
    const kind = attachmentKind(file.name, limits)
    if (kind === null) {
      return `${file.name}: 지원하지 않는 형식이에요(이미지 ${limits.image_extensions.join('·')}, 텍스트 ${limits.text_extensions.join('·')}, PDF).`
    }
    if (kind === 'image' && file.size > limits.image_upload_max_bytes) {
      return `${file.name}: 이미지는 ${megabytes(limits.image_upload_max_bytes)}까지 보낼 수 있어요.`
    }
    if (kind === 'pdf' && file.size > limits.pdf_max_bytes) {
      return `${file.name}: PDF는 ${megabytes(limits.pdf_max_bytes)}까지 보낼 수 있어요.`
    }
    if (kind === 'text' && file.size > limits.text_max_bytes) {
      return `${file.name}: 텍스트 파일은 ${Math.floor(limits.text_max_bytes / 1024)}KB까지 보낼 수 있어요.`
    }
  }
  return null
}

/** 글이 비어 있으면 보낼 수 없다(기본 질문을 넣지 않는다). 첨부가 있는데 글이 없을 때의 안내. */
export function attachmentHint(text: string, fileCount: number): string | null {
  return fileCount > 0 && !text.trim() ? '파일과 함께 보낼 질문을 적어 주세요.' : null
}

/** 서버가 내려준 첨부의 주소(썸네일은 이미지만) */
export function attachmentUrl(id: string, thumb = false): string {
  return `/api/attachments/${encodeURIComponent(id)}${thumb ? '?thumb=1' : ''}`
}
