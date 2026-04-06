"""
Unified Data Models - Central schema for all agency data.
This module defines the canonical data structures used across all projects.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class StoreType(str, Enum):
    BAKUDAN = "bakudan"
    RAW_SUSHI = "raw_sushi"
    COPPER = "copper"
    IFT = "ift"
    OTHER = "other"


class StoreLocation(str, Enum):
    THE_RIM = "the_rim"      # B1
    STONE_OAK = "stone_oak"  # B2
    BANDERA = "bandera"      # B3
    STOCKTON = "stockton"    # Raw Sushi
    TEXAS = "texas"          # Copper, IFT


class ProjectStatus(str, Enum):
    ONLINE = "online"
    WARNING = "warning"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


# ============================================
# Store Models
# ============================================

class Store(BaseModel):
    """Represents a physical store location."""
    id: str
    name: str
    store_type: StoreType
    location: StoreLocation
    city: str = "San Antonio"
    state: str = "TX"
    status: ProjectStatus = ProjectStatus.UNKNOWN
    timezone: str = "America/Chicago"

    # Metrics (updated from various sources)
    last_revenue_update: Optional[datetime] = None
    last_sync_update: Optional[datetime] = None


class StoreMetrics(BaseModel):
    """Aggregated metrics for a store."""
    store_id: str
    date: datetime

    # Revenue
    total_revenue: float = 0.0
    order_count: int = 0
    average_order_value: float = 0.0

    # Marketing
    marketing_spend: float = 0.0
    marketing_revenue: float = 0.0
    roas: float = 0.0
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    ctr: float = 0.0
    cvr: float = 0.0

    # Reviews
    google_reviews: int = 0
    yelp_reviews: int = 0
    responses_sent: int = 0
    avg_rating: float = 0.0

    # POS Sync
    orders_synced: int = 0
    sync_errors: int = 0
    last_sync: Optional[datetime] = None


# ============================================
# Project Models
# ============================================

class Project(BaseModel):
    """Represents an agency project/system."""
    id: str
    name: str
    description: str
    status: ProjectStatus = ProjectStatus.UNKNOWN
    last_check: Optional[datetime] = None

    # Connected stores
    store_ids: list[str] = Field(default_factory=list)

    # Metrics
    metrics: dict = Field(default_factory=dict)


class ProjectHealth(BaseModel):
    """Health status for a project."""
    project_id: str
    timestamp: datetime
    is_healthy: bool = True
    error_count: int = 0
    warning_count: int = 0
    last_error: Optional[str] = None
    uptime_percent: float = 100.0


# ============================================
# Unified Dashboard Models
# ============================================

class DashboardOverview(BaseModel):
    """Complete overview of all projects and stores."""
    timestamp: datetime

    # Summary stats
    total_projects: int = 0
    active_projects: int = 0
    total_stores: int = 0
    online_stores: int = 0

    # Revenue
    total_revenue_7d: float = 0.0
    total_revenue_30d: float = 0.0

    # Marketing
    total_spend: float = 0.0
    total_roas: float = 0.0

    # Tasks
    total_tasks: int = 0
    pending_tasks: int = 0
    overdue_tasks: int = 0

    # Projects list
    projects: list[Project] = Field(default_factory=list)

    # Stores list
    stores: list[Store] = Field(default_factory=list)

    # Alerts
    alerts: list[Alert] = Field(default_factory=list)


class Alert(BaseModel):
    """System alert."""
    id: str
    severity: str = "info"  # info, warning, error, critical
    title: str
    description: str
    project_id: Optional[str] = None
    store_id: Optional[str] = None
    timestamp: datetime
    is_resolved: bool = False


# ============================================
# Data Sync Models
# ============================================

class SyncJob(BaseModel):
    """Represents a data synchronization job."""
    id: str
    source: str  # e.g., "marketing", "taskflow", "review-mcp"
    target: str = "unified-db"
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    records_synced: int = 0
    errors: list[str] = Field(default_factory=list)


# ============================================
# Constants
# ============================================

# All stores in the system
ALL_STORES = {
    "B1": Store(
        id="B1",
        name="Bakudan 1 - THE RIM",
        store_type=StoreType.BAKUDAN,
        location=StoreLocation.THE_RIM,
        city="San Antonio",
        state="TX"
    ),
    "B2": Store(
        id="B2",
        name="Bakudan 2 - STONE OAK",
        store_type=StoreType.BAKUDAN,
        location=StoreLocation.STONE_OAK,
        city="San Antonio",
        state="TX"
    ),
    "B3": Store(
        id="B3",
        name="Bakudan 3 - BANDERA",
        store_type=StoreType.BAKUDAN,
        location=StoreLocation.BANDERA,
        city="San Antonio",
        state="TX"
    ),
    "RAW": Store(
        id="RAW",
        name="Raw Sushi - Stockton",
        store_type=StoreType.RAW_SUSHI,
        location=StoreLocation.STOCKTON,
        city="Stockton",
        state="CA"
    ),
    "COPPER": Store(
        id="COPPER",
        name="Copper",
        store_type=StoreType.COPPER,
        location=StoreLocation.TEXAS,
        city="San Antonio",
        state="TX"
    ),
    "IFT": Store(
        id="IFT",
        name="IFT",
        store_type=StoreType.IFT,
        location=StoreLocation.TEXAS,
        city="Texas",
        state="TX"
    ),
}

# All projects — synced with E:\Project\Master\
ALL_PROJECTS = {
    "agentai-agency": Project(
        id="agentai-agency",
        name="AgentAI Agency",
        description="AI Company OS — orchestrator, agents, control plane",
        store_ids=[],
    ),
    "BakudanWebsite_Sub": Project(
        id="BakudanWebsite_Sub",
        name="Bakudan Ramen Website",
        description="Official restaurant website — menu, locations, ordering",
        store_ids=["B1", "B2", "B3"],
    ),
    "BakudanWebsite_Sub2": Project(
        id="BakudanWebsite_Sub2",
        name="Bakudan Ramen Website v2",
        description="Secondary iteration of restaurant website",
        store_ids=["B1", "B2", "B3"],
    ),
    "RawWebsite": Project(
        id="RawWebsite",
        name="Raw Sushi Bistro Website",
        description="Restaurant website — menu, blog, analytics",
        store_ids=["RAW"],
    ),
    "dashboard-taskflow": Project(
        id="dashboard-taskflow",
        name="TaskFlow Dashboard",
        description="Project management — tasks, calendar, notifications, PWA",
        store_ids=["B1", "B2", "B3", "RAW"],
    ),
    "growth-dashboard": Project(
        id="growth-dashboard",
        name="Growth Dashboard",
        description="Growth analytics dashboard on Cloudflare Pages",
        store_ids=["B1", "B2", "B3"],
    ),
    "integration-full": Project(
        id="integration-full",
        name="Toast POS Integration",
        description="Desktop app — Toast POS to QuickBooks sync",
        store_ids=["B1", "B2", "B3", "RAW", "COPPER", "IFT"],
    ),
    "review-dashboard": Project(
        id="review-dashboard",
        name="ReviewOps Dashboard",
        description="Next.js frontend for review management system",
        store_ids=["B1", "B2", "B3", "RAW"],
    ),
    "review-management": Project(
        id="review-management",
        name="Review MCP Server",
        description="MCP server for Yelp & Google review management",
        store_ids=["B1", "B2", "B3", "RAW"],
    ),
    "review-system": Project(
        id="review-system",
        name="Review Automation System",
        description="Auto-fetch reviews, AI reply generation, auto-post",
        store_ids=["B1", "B2", "B3", "RAW"],
    ),
    "marketing": Project(
        id="marketing",
        name="Marketing Site",
        description="Marketing campaigns and assets (marketing.bakudanramen.com)",
        store_ids=["B1", "B2", "B3"],
    ),
}
