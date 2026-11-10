# Test Knowledge Base
TEST_FAQS = [
    {
        "category": "Account & Login",
        "question": "How do I reset my password?",
        "answer": 'Click "Forgot Password" on the login screen, enter your registered email address, and follow the instructions sent to your inbox to set a new password.',
    },
    {
        "category": "Account & Login",
        "question": "How can I update my email address or phone number?",
        "answer": 'Log in to your account, go to the "Account Settings" or "Profile" page, edit your contact details, and save the changes.',
    },
    {
        "category": "Account & Login",
        "question": "How do I delete or deactivate my account?",
        "answer": 'Go to your account settings and select "Delete Account," or reach out to our support team to process the request for you.',
    },
    {
        "category": "Billing & Payments",
        "question": "What payment methods do you accept?",
        "answer": "We accept major credit and debit cards (Visa, MasterCard, American Express, Discover), PayPal, and Apple Pay.",
    },
    {
        "category": "Billing & Payments",
        "question": "Why was I charged twice or see a pending authorization?",
        "answer": "A pending authorization is a temporary hold to verify your card details and usually drops off within 3 to 5 business days. If you see a duplicate completed charge, please contact support with your order number.",
    },
    {
        "category": "Billing & Payments",
        "question": "How do I get a copy of my invoice or receipt?",
        "answer": 'Log in to your account, navigate to "Order History" or "Billing," and click on the specific transaction to download your receipt.',
    },
    {
        "category": "Shipping & Orders",
        "question": "How do I track my order?",
        "answer": "Once your order ships, you will receive a confirmation email containing a tracking number and a link to follow your package's delivery status.",
    },
    {
        "category": "Shipping & Orders",
        "question": "Can I change or cancel my order after it has been placed?",
        "answer": "Orders can only be modified or cancelled within 1 hour of placement. After that window, the order moves to fulfillment and must be returned after arrival.",
    },
    {
        "category": "Shipping & Orders",
        "question": "What is your return and refund policy?",
        "answer": "You can return unused items in their original packaging within 30 days of delivery for a full refund minus shipping costs. Visit our returns portal to start a request.",
    },
]


# Test Customer Account Table
# PK: customer_id (S). Access pattern: get customer by id.
CUSTOMER_TABLE = [
    {
        "customer_id": "C001",
        "name": "sam",
        "tier": "standard",
    },
    {
        "customer_id": "C002",
        "name": "pam",
        "tier": "premium",
    },
]

# Test Orders Table
# PK: customer_id (S), SK: order_id (S).
# Access patterns: list a customer's orders (Query on PK), get one order (PK + SK).
# status is one of: placed, delivering, delivered, refunded
# delivered_at is set once status reaches delivered; the 30-day refund window counts from it.
ORDER_TABLE = [
    {
        "customer_id": "C001",
        "order_id": "O001",
        "item": "iPhone 16 Pro Max",
        "status": "delivered",
        "created_at": "2026-10-20T14:03:00Z",
        "delivered_at": "2026-10-23T16:40:00Z",
    },
    {
        "customer_id": "C002",
        "order_id": "O002",
        "item": "Samsung Galaxy 9",
        "status": "delivered",
        "created_at": "2026-11-03T09:15:00Z",
        "delivered_at": "2026-11-06T11:20:00Z",
    },
    {
        "customer_id": "C001",
        "order_id": "O003",
        "item": "MacBook Air",
        "status": "placed",
        "created_at": "2026-10-20T14:03:00Z",
    },
    {
        "customer_id": "C002",
        "order_id": "O004",
        "item": "Chromebook 10 inch",
        "status": "placed",
        "created_at": "2026-11-03T09:15:00Z",
    },
    {
        "customer_id": "C001",
        "order_id": "O005",
        "item": "AirPods Pro",
        "status": "delivered",
        "created_at": "2026-08-01T10:00:00Z",
        "delivered_at": "2026-08-04T15:00:00Z",  # outside the 30-day refund window
    },
]

# Test Events Table (append-only audit log, written by tools only, never by the model)
# PK: customer_id (S), SK: created_at#event_id (S, sorts by time).
# Access pattern: a customer's history of actions (Query on PK).
EVENTS_TABLE = []
