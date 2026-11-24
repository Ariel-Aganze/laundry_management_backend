from rest_framework.routers import SimpleRouter

from .views import ReceiptViewSet

router = SimpleRouter()
router.register("", ReceiptViewSet, basename="receipt")
urlpatterns = router.urls
