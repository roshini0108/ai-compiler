from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class FieldType(str, Enum):
    uuid = "uuid"
    string = "string"
    email = "email"
    integer = "integer"
    float_ = "float"
    boolean = "boolean"
    datetime = "datetime"
    text = "text"
    json = "json"
    ref = "ref"  # foreign key reference


class RelationType(str, Enum):
    one_to_many = "one_to_many"
    many_to_one = "many_to_one"
    many_to_many = "many_to_many"
    one_to_one = "one_to_one"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class AuthStrategy(str, Enum):
    jwt = "jwt"
    session = "session"
    oauth2 = "oauth2"


# ─── IR Sub-models ─────────────────────────────────────────────────────────────

class IRField(BaseModel):
    id: str
    name: str
    type: FieldType
    required: bool = True
    unique: bool = False
    primary: bool = False
    default: Optional[str] = None
    ref_entity: Optional[str] = None  # used when type == ref


class IRRelation(BaseModel):
    type: RelationType
    target_entity: str
    via_field: str


class IREntity(BaseModel):
    id: str
    name: str
    fields: list[IRField]
    relations: list[IRRelation] = []


class IREndpoint(BaseModel):
    id: str
    method: HttpMethod
    path: str
    description: str
    entity: str
    required_roles: list[str] = []
    request_fields: list[str] = []   # field ids from entity
    response_fields: list[str] = []  # field ids from entity


class IRPage(BaseModel):
    id: str
    name: str
    path: str
    entity: Optional[str] = None
    required_roles: list[str] = []
    components: list[str] = []       # e.g. ["table", "form", "chart"]


class IRRole(BaseModel):
    id: str
    name: str
    description: str
    inherits: Optional[str] = None   # role inheritance


class IRPermission(BaseModel):
    role_id: str
    endpoint_id: str
    allowed: bool


class IRPlan(BaseModel):
    id: str
    name: str
    price: float = 0.0
    payment_required: bool = False
    features: list[str] = []


class IRBusinessRule(BaseModel):
    id: str
    description: str
    applies_to: str        # entity or feature id
    roles: list[str] = []
    condition: str | None = None         # plain english condition
    effect: str            # plain english effect


# ─── Master IR ─────────────────────────────────────────────────────────────────

class IntermediateRepresentation(BaseModel):
    ir_version: str = "1.0"
    app_name: str
    domain: str
    description: str
    entities: list[IREntity]
    endpoints: list[IREndpoint] = []
    pages: list[IRPage] = []
    roles: list[IRRole]
    permissions: list[IRPermission] = []
    plans: list[IRPlan] = []
    business_rules: list[IRBusinessRule] = []
    auth_strategy: AuthStrategy = AuthStrategy.jwt
    features: list[str] = []


# ─── Intent model (Stage 1 output) ─────────────────────────────────────────────

class IntentModel(BaseModel):
    entities: list[str] = Field(description="Core data entities e.g. User, Contact")
    features: list[str] = Field(description="Product features e.g. login, dashboard")
    roles: list[str] = Field(description="User roles e.g. admin, viewer")
    integrations: list[str] = Field(description="External integrations e.g. payments")
    constraints: list[str] = Field(description="Business constraints e.g. admins only")
    plans: list[str] = Field(default=[], description="Pricing plans e.g. free, premium")
