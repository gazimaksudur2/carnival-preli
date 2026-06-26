from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Language(str, Enum):
    EN = "en"
    BN = "bn"
    MIXED = "mixed"


class Channel(str, Enum):
    IN_APP_CHAT = "in_app_chat"
    CALL_CENTER = "call_center"
    EMAIL = "email"
    MERCHANT_PORTAL = "merchant_portal"
    FIELD_AGENT = "field_agent"


class UserType(str, Enum):
    CUSTOMER = "customer"
    MERCHANT = "merchant"
    AGENT = "agent"
    UNKNOWN = "unknown"


class TransactionType(str, Enum):
    TRANSFER = "transfer"
    PAYMENT = "payment"
    CASH_IN = "cash_in"
    CASH_OUT = "cash_out"
    SETTLEMENT = "settlement"
    REFUND = "refund"


class TransactionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    REVERSED = "reversed"


class EvidenceVerdict(str, Enum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    INSUFFICIENT_DATA = "insufficient_data"


class CaseType(str, Enum):
    WRONG_TRANSFER = "wrong_transfer"
    PAYMENT_FAILED = "payment_failed"
    REFUND_REQUEST = "refund_request"
    DUPLICATE_PAYMENT = "duplicate_payment"
    MERCHANT_SETTLEMENT_DELAY = "merchant_settlement_delay"
    AGENT_CASH_IN_ISSUE = "agent_cash_in_issue"
    PHISHING_OR_SOCIAL_ENGINEERING = "phishing_or_social_engineering"
    OTHER = "other"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Department(str, Enum):
    CUSTOMER_SUPPORT = "customer_support"
    DISPUTE_RESOLUTION = "dispute_resolution"
    PAYMENTS_OPS = "payments_ops"
    MERCHANT_OPERATIONS = "merchant_operations"
    AGENT_OPERATIONS = "agent_operations"
    FRAUD_RISK = "fraud_risk"


class TransactionItem(BaseModel):
    transaction_id: str
    timestamp: str
    type: TransactionType
    amount: float
    counterparty: str
    status: TransactionStatus


class AnalyzeRequest(BaseModel):
    ticket_id: str
    complaint: str
    language: Optional[Language] = None
    channel: Optional[Channel] = None
    user_type: Optional[UserType] = None
    campaign_context: Optional[str] = None
    transaction_history: Optional[List[TransactionItem]] = Field(default_factory=list)
    metadata: Optional[dict] = None


class AnalyzeResponse(BaseModel):
    ticket_id: str
    relevant_transaction_id: Optional[str]
    evidence_verdict: EvidenceVerdict
    case_type: CaseType
    severity: Severity
    department: Department
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: Optional[float] = None
    reason_codes: Optional[List[str]] = None
