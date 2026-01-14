# Templating Extension

Module: `rail_django.extensions.templating`

- Decorators `@model_pdf_template` and `@pdf_template` register PDF endpoints.
- Helpers: `render_pdf(...)`, `PdfBuilder()`, and pluggable renderers.
- Endpoints: `/api/templates/<template_path>/<pk>/`, `/api/templates/catalog/`,
  `/api/templates/preview/...`, plus async job status/download endpoints under
  `/api/templates/jobs/...`.
- Optional post-processing for watermarks, page stamps, encryption, and signatures.
- Optional dependencies: `pypdf`, `pyhanko`, `wkhtmltopdf` binary.
