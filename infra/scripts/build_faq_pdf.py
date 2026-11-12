# /// script
# requires-python = ">=3.14"
# dependencies = ["reportlab>=4.0"]
# ///
"""Build data/faqs/company-faqs.pdf, the source document for the FAQ Knowledge Base.

Run from infra/:
    uv run scripts/build_faq_pdf.py

The first nine entries match TEST_FAQS in agents/app/agents/test_data.py. The rest use specific,
made-up numbers, codes and names, so a Knowledge Base answer is easy to check against the source.
"""

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

OUTPUT = Path(__file__).resolve().parents[2] / "data" / "faqs" / "company-faqs.pdf"

FAQS: dict[str, list[tuple[str, str]]] = {
    "Account & Login": [
        (
            "How do I reset my password?",
            (
                'Click "Forgot Password" on the login screen, enter your registered email address, and follow '
                "the instructions sent to your inbox to set a new password. Reset links expire after 45 minutes."
            ),
        ),
        (
            "How can I update my email address or phone number?",
            (
                'Log in to your account, go to the "Account Settings" or "Profile" page, edit your contact '
                "details, and save the changes."
            ),
        ),
        (
            "How do I delete or deactivate my account?",
            (
                'Go to your account settings and select "Delete Account," or reach out to our support team to '
                "process the request for you. Deleted accounts can be restored for 14 days; after that, all "
                "order history and loyalty points are permanently removed."
            ),
        ),
        (
            "What happens after too many failed login attempts?",
            (
                "After 6 failed login attempts in a row, your account is locked for 20 minutes. You can unlock it "
                "sooner by resetting your password."
            ),
        ),
        (
            "Do you support two-factor authentication?",
            (
                "Yes. You can turn on two-factor authentication under Account Settings > Security using an "
                "authenticator app or SMS. Each account gets 10 single-use backup codes."
            ),
        ),
    ],
    "Billing & Payments": [
        (
            "What payment methods do you accept?",
            (
                "We accept major credit and debit cards (Visa, MasterCard, American Express, Discover), PayPal, "
                "and Apple Pay. We do not accept cryptocurrency, checks, or cash on delivery."
            ),
        ),
        (
            "Why was I charged twice or see a pending authorization?",
            (
                "A pending authorization is a temporary hold to verify your card details and usually drops off "
                "within 3 to 5 business days. If you see a duplicate completed charge, please contact support "
                "with your order number."
            ),
        ),
        (
            "How do I get a copy of my invoice or receipt?",
            (
                'Log in to your account, navigate to "Order History" or "Billing," and click on the specific '
                "transaction to download your receipt."
            ),
        ),
        (
            "Can I pay in installments?",
            (
                "Orders between $150 and $2,000 can be split into 4 interest-free payments, charged every 2 weeks. "
                'Choose "Pay in 4" at checkout.'
            ),
        ),
        (
            "Do gift cards expire?",
            (
                "No. Gift cards never expire and have no fees. Gift cards cannot be redeemed for cash, except "
                "where required by law, and a maximum of 3 gift cards can be used on a single order."
            ),
        ),
        (
            "Do you price match?",
            (
                "If the price of an item you bought from us drops within 14 days of purchase, we refund the "
                "difference once per item. We do not match competitor prices, flash sales, or clearance prices."
            ),
        ),
    ],
    "Shipping & Orders": [
        (
            "How do I track my order?",
            (
                "Once your order ships, you will receive a confirmation email containing a tracking number and a "
                "link to follow your package's delivery status."
            ),
        ),
        (
            "Can I change or cancel my order after it has been placed?",
            (
                "Orders can only be modified or cancelled within 1 hour of placement. After that window, the "
                "order moves to fulfillment and must be returned after arrival."
            ),
        ),
        (
            "How much does shipping cost?",
            (
                "Standard shipping (5 to 7 business days) is free on orders of $49 or more and $5.99 otherwise. "
                "Express shipping (2 business days) costs $12.99. Overnight shipping costs $24.99 and must be "
                "ordered before 1:00 PM Eastern Time."
            ),
        ),
        (
            "Do you ship internationally?",
            (
                "We ship to the United States, Canada, the United Kingdom, Australia, and the European Union. "
                "International orders take 7 to 14 business days, and the customer pays any import duties or "
                "taxes. We do not ship to P.O. boxes outside the United States."
            ),
        ),
        (
            "What if my package is marked delivered but I did not receive it?",
            (
                "Wait 48 hours, since carriers sometimes mark packages delivered early, and check with neighbours. "
                "If it still has not arrived, contact support within 10 days of the delivery date and we will open "
                "a carrier investigation."
            ),
        ),
    ],
    "Returns & Refunds": [
        (
            "What is your return and refund policy?",
            (
                "You can return unused items in their original packaging within 30 days of delivery for a full "
                "refund minus shipping costs. Visit our returns portal to start a request."
            ),
        ),
        (
            "How long does a refund take?",
            (
                "Refunds to the original payment method are issued within 5 to 7 business days after the "
                "warehouse receives your return. Refunds taken as store credit are issued instantly and include "
                "a 10% bonus."
            ),
        ),
        (
            "Is there a restocking fee?",
            (
                "Opened electronics have a 15% restocking fee. Unopened electronics and all other product "
                "categories have no restocking fee."
            ),
        ),
        (
            "Which items cannot be returned?",
            (
                "Final-sale clearance items (marked with a red tag), personalized or engraved items, opened "
                "software, and gift cards cannot be returned."
            ),
        ),
        (
            "What should I do if my item arrived damaged?",
            (
                "Report damaged or defective items within 48 hours of delivery with at least 2 photos of the item "
                "and packaging. We ship a free replacement or issue a full refund, including original shipping."
            ),
        ),
    ],
    "Warranty": [
        (
            "What warranty do your products have?",
            (
                "Products from our in-house brand, Lumora, have a 2-year limited warranty. All other brands carry "
                "the manufacturer's warranty. The warranty covers manufacturing defects but not accidental damage, "
                "water damage, or normal wear."
            ),
        ),
        (
            "Do you offer an extended warranty?",
            (
                "Yes. The CarePlus extended protection plan adds 3 years of coverage, including accidental damage, "
                "for 12% of the item's price. It must be bought within 30 days of the original purchase."
            ),
        ),
    ],
    "Loyalty & Discounts": [
        (
            "How does the loyalty program work?",
            (
                "Members of our loyalty program, Orbit Rewards, earn 1 point per $1 spent. Every 100 points can be "
                "redeemed for $5 off a future order. Points expire after 12 months without account activity."
            ),
        ),
        (
            "What are the loyalty tiers?",
            (
                "Orbit Silver is the starting tier. Orbit Gold starts at $1,000 spent in a calendar year and earns "
                "1.5 points per $1 plus free express shipping. Orbit Platinum starts at $2,500 spent in a calendar "
                "year and earns 2 points per $1 plus free overnight shipping."
            ),
        ),
        (
            "Do you offer a student discount?",
            (
                "Students get 10% off full-price items after verifying their student status. The discount can be "
                "used on up to 5 orders per year and cannot be combined with other promo codes."
            ),
        ),
        (
            "Can I combine promo codes?",
            (
                "Only one promo code can be used per order. Loyalty point redemptions and gift cards can be "
                "combined with a promo code."
            ),
        ),
    ],
    "Contact & Support": [
        (
            "How do I contact customer support?",
            (
                "Call 1-800-555-0142, Monday to Friday 8:00 AM to 8:00 PM Eastern Time and Saturday 10:00 AM to "
                "4:00 PM Eastern Time. Live chat is available 24/7 from the Help page. Email support@example.com; "
                "we reply within 24 hours."
            ),
        ),
        (
            "What is your mailing address for returns?",
            (
                "Ship returns to Returns Center, 1200 Commerce Way, Suite 300, Columbus, OH 43215. Always include "
                "the return authorization number from the returns portal on the outside of the box."
            ),
        ),
    ],
}


def build(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    question = ParagraphStyle(
        "Question", parent=styles["Heading4"], spaceBefore=8, spaceAfter=2
    )

    story = [
        Paragraph("Customer Frequently Asked Questions", styles["Title"]),
        Spacer(1, 0.2 * inch),
    ]
    for category, entries in FAQS.items():
        story.append(Paragraph(category, styles["Heading2"]))
        for q, a in entries:
            story.append(Paragraph(f"Q: {q}", question))
            story.append(Paragraph(f"A: {a}", styles["BodyText"]))

    SimpleDocTemplate(
        str(path), pagesize=LETTER, title="Customer FAQs", author="aws-rag-solution"
    ).build(story)


if __name__ == "__main__":
    build(OUTPUT)
    print(f"Wrote {OUTPUT} ({sum(len(e) for e in FAQS.values())} FAQs)")
