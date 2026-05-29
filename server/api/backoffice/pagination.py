from rest_framework.pagination import PageNumberPagination


class BackofficePageNumberPagination(PageNumberPagination):
    """Numbered pagination for backoffice lists — the UI renders page numbers,
    so the response carries `count` and the client navigates with `?page=N`.

    Ordering comes from each view's queryset `.order_by(...)` (page-number
    pagination, unlike cursor, doesn't impose its own ordering), so every
    paginated view must order deterministically.
    """

    page_size = 20
