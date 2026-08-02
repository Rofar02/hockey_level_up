export function FormError({ message }: { message: string | null }) {
  if (message === null) {
    return null
  }
  return <p className="rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">{message}</p>
}
