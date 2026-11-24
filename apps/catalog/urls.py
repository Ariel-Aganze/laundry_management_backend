from rest_framework.routers import SimpleRouter

from .views import ServiceCategoryViewSet, ServiceItemViewSet

categories_router = SimpleRouter()
categories_router.register("", ServiceCategoryViewSet, basename="category")

services_router = SimpleRouter()
services_router.register("", ServiceItemViewSet, basename="service")
