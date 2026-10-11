function PageHeader({ eyebrow = 'Workspace', title, description, action }) {
  return <div className="page-header"><div><p className="overline">{eyebrow}</p><h1>{title}</h1>{description && <p className="page-subtitle">{description}</p>}</div>{action}</div>
}

export default PageHeader
