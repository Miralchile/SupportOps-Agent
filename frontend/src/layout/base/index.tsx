import './index.scss'

export function BaseLayout({ children }: { children?: React.ReactNode }) {
  return (
    <div className="base-layout">
      <div className="base-layout__content">{children}</div>
    </div>
  )
}
