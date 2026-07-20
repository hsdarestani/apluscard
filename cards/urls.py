from django.urls import path

from . import api, views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("health/", views.health, name="health"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("customer/", views.customer_dashboard, name="customer_dashboard"),
    path("staff/", views.staff_dashboard, name="staff_dashboard"),
    path("staff/charge/", views.staff_charge, name="staff_charge"),
    path("manager/", views.manager_dashboard, name="manager_dashboard"),
    path("manager/wallets/create/", views.manager_wallet_create, name="manager_wallet_create"),
    path("manager/wallets/<uuid:wallet_id>/", views.manager_wallet_detail, name="manager_wallet_detail"),
    path("manager/wallets/<uuid:wallet_id>/topup/", views.manager_topup, name="manager_topup"),
    path("manager/wallets/<uuid:wallet_id>/refund/", views.manager_refund, name="manager_refund"),
    path("manager/wallets/<uuid:wallet_id>/status/", views.manager_wallet_status, name="manager_wallet_status"),
    path("api/v1/me/", api.MeView.as_view(), name="api_me"),
    path("api/v1/wallet/", api.MyWalletView.as_view(), name="api_wallet"),
    path("api/v1/wallet/transactions/", api.MyTransactionsView.as_view(), name="api_wallet_transactions"),
    path("api/v1/staff/charge/", api.StaffChargeView.as_view(), name="api_staff_charge"),
    path("api/v1/manager/topup/", api.ManagerTopupView.as_view(), name="api_manager_topup"),
    path("api/v1/manager/refund/", api.ManagerRefundView.as_view(), name="api_manager_refund"),
]
