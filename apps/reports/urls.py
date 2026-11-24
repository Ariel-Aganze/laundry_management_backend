from django.urls import path

from .views import (
    CashierAnalyticsView,
    CustomerAnalyticsView,
    DashboardSummaryView,
    OverduePickupsView,
    PaymentAnalyticsView,
    RevenueAnalyticsView,
    ServiceAnalyticsView,
    UpcomingPickupsView,
)

dashboard_urlpatterns = [
    path("summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("pickups/", UpcomingPickupsView.as_view(), name="dashboard-pickups"),
    path("overdue/", OverduePickupsView.as_view(), name="dashboard-overdue"),
]

analytics_urlpatterns = [
    path("revenue/", RevenueAnalyticsView.as_view(), name="analytics-revenue"),
    path("services/", ServiceAnalyticsView.as_view(), name="analytics-services"),
    path("cashiers/", CashierAnalyticsView.as_view(), name="analytics-cashiers"),
    path("customers/", CustomerAnalyticsView.as_view(), name="analytics-customers"),
    path("payments/", PaymentAnalyticsView.as_view(), name="analytics-payments"),
]
