"""The sample helpdesk the demo seed creates: people, equipment and tickets with their history.

Everything is written relative to the moment of seeding (ticket ages, the steps after a ticket was
opened, warranty dates from today), so the demo looks the same whenever it is created. The seed
replays each step through the app's own rules, which is what keeps it consistent:

- tickets: an unassigned queue, work in progress, tickets waiting on the requester (SLA paused),
  two at risk, two breached, and resolved or closed ones, mostly within their targets;
- equipment: assigned, in stock, in repair and retired, two warranties running out this month.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from app.models.asset import AssetStatus, AssetType
from app.models.ticket import Category, Priority, TicketStatus
from app.models.user import Role


def minutes(n: float) -> timedelta:
    return timedelta(minutes=n)


def hours(n: float) -> timedelta:
    return timedelta(hours=n)


def days(n: float) -> timedelta:
    return timedelta(days=n)


DEMO_PASSWORD = "deskflow123"

# The documented sign-in accounts. They are never changed once they exist.
ADMIN = "admin@deskflow.dev"
AGENT = "agent@deskflow.dev"
GRACE = "user@deskflow.dev"
DEMO_USERS = [
    (ADMIN, "Ada Admin", Role.ADMIN),
    (AGENT, "Alan Agent", Role.AGENT),
    (GRACE, "Grace User", Role.REQUESTER),
]

# Colleagues who raise tickets. They cannot sign in: their password is random and never stored.
ERIK = "erik.lindqvist@deskflow.dev"
SARA = "sara.nilsson@deskflow.dev"
JOHAN = "johan.berg@deskflow.dev"
AMIRA = "amira.haddad@deskflow.dev"
LUKAS = "lukas.meyer@deskflow.dev"
PRIYA = "priya.sharma@deskflow.dev"
MATEO = "mateo.garcia@deskflow.dev"
DEMO_REQUESTERS = [
    (ERIK, "Erik Lindqvist"),
    (SARA, "Sara Nilsson"),
    (JOHAN, "Johan Berg"),
    (AMIRA, "Amira Haddad"),
    (LUKAS, "Lukas Meyer"),
    (PRIYA, "Priya Sharma"),
    (MATEO, "Mateo García"),
]


# Steps. `after` is measured from the start of the ticket (or the asset's registration) they
# belong to, and `by` is the email of the person taking the step.


@dataclass(frozen=True)
class Assign:
    after: timedelta
    to: str
    by: str = AGENT


@dataclass(frozen=True)
class Reply:
    """A comment. From staff it is a public reply, and the first one stops the response clock."""

    after: timedelta
    by: str
    body: str


@dataclass(frozen=True)
class Note:
    """An internal note, only visible to staff."""

    after: timedelta
    body: str
    by: str = AGENT


@dataclass(frozen=True)
class Status:
    after: timedelta
    to: TicketStatus
    by: str = AGENT


@dataclass(frozen=True)
class Escalate:
    after: timedelta
    to: Priority
    by: str = AGENT


@dataclass(frozen=True)
class Link:
    """Link the ticket to a piece of equipment, by its key in DEMO_ASSETS."""

    after: timedelta
    asset: str
    by: str = AGENT


@dataclass(frozen=True)
class AssetAssign:
    """Hand equipment to someone. In a ticket's history `asset` names it; in an asset's, it is
    left empty and means that asset."""

    after: timedelta
    to: str
    asset: str = ""
    by: str = ADMIN


@dataclass(frozen=True)
class AssetStatusChange:
    """Send equipment for repair, back to stock or into retirement."""

    after: timedelta
    to: AssetStatus
    asset: str = ""
    by: str = ADMIN


TicketStep = Assign | Reply | Note | Status | Escalate | Link | AssetAssign | AssetStatusChange
AssetStep = AssetAssign | AssetStatusChange


@dataclass(frozen=True)
class DemoTicket:
    title: str
    description: str
    category: Category
    priority: Priority
    requester: str
    age: timedelta  # how long ago it was opened
    steps: tuple[TicketStep, ...] = ()
    logged_by: str | None = None  # staff who logged it on the requester's behalf


@dataclass(frozen=True)
class DemoAsset:
    key: str
    type: AssetType
    manufacturer: str
    model: str
    serial_number: str
    location: str
    purchased: timedelta  # how long ago
    warranty_left: timedelta | None  # from today; negative when it has run out
    registered: timedelta = days(45)  # when it was entered into DeskFlow, how long ago
    notes: str | None = None
    steps: tuple[AssetStep, ...] = field(default=())


def _warranty(years: int, purchased: timedelta) -> timedelta:
    return days(365 * years) - purchased


DEMO_ASSETS = [
    DemoAsset(
        "grace-laptop",
        AssetType.LAPTOP,
        "Lenovo",
        "ThinkPad T14 Gen 4",
        "PF4KX2B7",
        "Stockholm HQ",
        purchased=days(410),
        warranty_left=_warranty(3, days(410)),
        steps=(AssetAssign(days(1), GRACE),),
    ),
    DemoAsset(
        "grace-monitor",
        AssetType.MONITOR,
        "Dell",
        "P2723DE 27-inch",
        "CN0H7X9V7429",
        "Service desk, floor 1",
        purchased=days(200),
        warranty_left=_warranty(3, days(200)),
    ),
    DemoAsset(
        "erik-laptop",
        AssetType.LAPTOP,
        "Dell",
        "Latitude 5440",
        "7HQ2LZ3",
        "Göteborg office",
        purchased=days(300),
        warranty_left=_warranty(3, days(300)),
        steps=(AssetAssign(days(1), ERIK),),
    ),
    DemoAsset(
        "priya-laptop",
        AssetType.LAPTOP,
        "Apple",
        "MacBook Pro 14-inch (M3 Pro)",
        "K7QW9XH2LT",
        "Stockholm HQ",
        purchased=days(150),
        warranty_left=_warranty(3, days(150)),
        notes="AppleCare for Enterprise, 3 years.",
        steps=(AssetAssign(days(1), PRIYA),),
    ),
    DemoAsset(
        "johan-laptop",
        AssetType.LAPTOP,
        "HP",
        "EliteBook 840 G10",
        "5CG3412KXN",
        "Stockholm HQ",
        purchased=days(3 * 365 - 12),
        warranty_left=days(12),
        notes="Warranty ends this month: decide on an extension or a replacement.",
        steps=(AssetAssign(days(1), JOHAN),),
    ),
    DemoAsset(
        "amira-phone",
        AssetType.PHONE,
        "Samsung",
        "Galaxy S23",
        "R5CW31QXYZA",
        "Stockholm HQ",
        purchased=days(500),
        warranty_left=_warranty(2, days(500)),
        steps=(AssetAssign(days(1), AMIRA),),
    ),
    DemoAsset(
        "spare-phone",
        AssetType.PHONE,
        "Apple",
        "iPhone 15",
        "F2LXK9QPN1",
        "Service desk, floor 1",
        purchased=days(60),
        warranty_left=_warranty(1, days(60)),
        notes="Spare handset for same-day replacements.",
    ),
    DemoAsset(
        "printer-floor2",
        AssetType.PRINTER,
        "HP",
        "LaserJet Enterprise M611dn",
        "PHBQK48211",
        "Stockholm HQ, floor 2",
        purchased=days(900),
        warranty_left=_warranty(3, days(900)),
        notes="Shared printer, queue \\\\print01\\HQ-F2. Service contract with HP.",
    ),
    DemoAsset(
        "ap-saturnus",
        AssetType.NETWORK,
        "Cisco Meraki",
        "MR46 access point",
        "Q3AB-7K2L-9XYZ",
        "Stockholm HQ, meeting room Saturnus",
        purchased=days(700),
        warranty_left=None,
        notes="Ceiling mounted. Lifetime hardware warranty, no end date.",
    ),
    DemoAsset(
        "spare-laptop",
        AssetType.LAPTOP,
        "Lenovo",
        "ThinkPad T14 Gen 4",
        "PF4KX9C1",
        "IT storage room",
        purchased=days(30),
        warranty_left=_warranty(3, days(30)),
        registered=days(25),
    ),
    DemoAsset(
        "lukas-dock",
        AssetType.PERIPHERAL,
        "Lenovo",
        "ThinkPad Universal USB-C Dock",
        "ZK40Y1F3",
        "Stockholm HQ",
        purchased=days(380),
        warranty_left=_warranty(3, days(380)),
        steps=(AssetAssign(days(1), LUKAS),),
    ),
    DemoAsset(
        "stock-monitor",
        AssetType.MONITOR,
        "Dell",
        "UltraSharp U2724D",
        "CN0J6R2M8812",
        "IT storage room",
        purchased=days(3 * 365 - 25),
        warranty_left=days(25),
    ),
    DemoAsset(
        "mateo-desktop",
        AssetType.DESKTOP,
        "HP",
        "Z2 Tower G9 Workstation",
        "CZC2387T5Q",
        "Stockholm HQ, design studio",
        purchased=days(800),
        warranty_left=_warranty(3, days(800)),
        steps=(AssetAssign(days(1), MATEO),),
    ),
    DemoAsset(
        "sara-laptop",
        AssetType.LAPTOP,
        "Lenovo",
        "ThinkPad X1 Carbon Gen 10",
        "PF3NB8LQ",
        "Malmö office",
        purchased=days(3 * 365 + 40),
        warranty_left=days(-40),
        notes="Out of warranty. Due for replacement in the next refresh.",
        steps=(AssetAssign(days(1), SARA),),
    ),
    DemoAsset(
        "old-laptop",
        AssetType.LAPTOP,
        "Dell",
        "Latitude 7490",
        "4XK8KP2",
        "IT storage room",
        purchased=days(6 * 365),
        warranty_left=days(-3 * 365),
        notes="Disk wiped (NIST 800-88 purge) and collected for recycling.",
        steps=(AssetStatusChange(days(20), AssetStatus.RETIRED),),
    ),
]


DEMO_TICKETS = [
    # --- Open: waiting on the requester (SLA paused) ---------------------------------------
    DemoTicket(
        "Laptop battery drains in under two hours",
        "My laptop goes from full to empty in less than two hours, even with only Outlook and "
        "Teams open. It used to last a whole day. It also gets quite warm underneath.",
        Category.HARDWARE,
        Priority.P3,
        GRACE,
        age=hours(26),
        steps=(
            Assign(minutes(35), AGENT),
            Link(minutes(36), "grace-laptop"),
            Reply(
                minutes(50),
                AGENT,
                "Hi Grace, thanks for reporting this. A battery that empties that fast is usually "
                "worn out rather than a settings problem. Could you drop the laptop off at the "
                "service desk on floor 1? We'll run the vendor diagnostics and replace the "
                "battery if it fails. It takes about an hour.",
            ),
            Reply(
                hours(2),
                GRACE,
                "Thanks! I'm in workshops all day today, I'll bring it by tomorrow morning.",
            ),
            Status(hours(2) + minutes(10), TicketStatus.PENDING),
            Note(
                hours(2) + minutes(12),
                "Battery report: design capacity 52 Wh, full charge 19 Wh (36%). A spare battery "
                "(FRU 5B10W51826) is on the shelf and reserved for this.",
            ),
        ),
    ),
    DemoTicket(
        "Teams calls lose audio after about ten minutes",
        "In longer Teams calls the other people go silent after roughly ten minutes, while they "
        "can still hear me. Leaving and rejoining fixes it for another ten minutes.",
        Category.SOFTWARE,
        Priority.P3,
        PRIYA,
        age=days(3),
        steps=(
            Assign(hours(2), AGENT),
            Reply(
                hours(2) + minutes(15),
                AGENT,
                "Hi Priya, could you try one call with a wired headset (you can borrow one from "
                "the service desk) instead of the Bluetooth one? If the audio stays up, the "
                "cause is the Bluetooth hands-free profile rather than Teams.",
            ),
            Status(hours(2) + minutes(20), TicketStatus.PENDING),
            Reply(
                days(1) + hours(2),
                AGENT,
                "Just checking in: have you had a chance to try the wired headset?",
            ),
        ),
    ),
    # --- Open: breached ----------------------------------------------------------------------
    DemoTicket(
        "VPN disconnects every few minutes when working from home",
        "Since Monday the VPN drops every 3-5 minutes when I work from home, so Teams calls and "
        "file copies keep failing. It reconnects by itself but I lose whatever I was doing.",
        Category.NETWORK,
        Priority.P3,
        ERIK,
        age=hours(11),
        steps=(
            Escalate(minutes(20), Priority.P2),
            Assign(minutes(25), AGENT),
            Reply(
                minutes(40),
                AGENT,
                "Hi Erik, I've raised the priority since you can't work remotely. Which network "
                "are you on at home, and does it also drop on your phone's hotspot? That tells us "
                "whether it's the home router or the VPN client.",
            ),
            Reply(
                hours(1) + minutes(30),
                ERIK,
                "Home fibre over Wi-Fi. I tried the hotspot during lunch and it stayed up for "
                "40 minutes, so maybe it's the router?",
            ),
            Note(
                hours(2),
                "Firewall logs show the IKE rekey failing every ~5 min for his tunnel, only from "
                "his home IP. Likely the ISP router's IPsec passthrough. Asked the network team "
                "whether we can move him to the SSL VPN profile.",
            ),
            Reply(
                hours(2) + minutes(10),
                AGENT,
                "Thanks, that helps. It looks like your router interrupts the VPN's key renewal. "
                "I'm checking with the network team whether we can switch you to a VPN profile "
                "that avoids it.",
            ),
        ),
    ),
    DemoTicket(
        "Several keys on my keyboard are sticking",
        "The E and R keys stick and sometimes type twice. I've cleaned it with compressed air "
        "but it hasn't helped. It's the wired keyboard at my desk in the design studio.",
        Category.HARDWARE,
        Priority.P4,
        MATEO,
        age=hours(30),
    ),
    # --- Open: at risk -------------------------------------------------------------------
    DemoTicket(
        "Outlook keeps asking for my password",
        "Every hour or so Outlook pops up a sign-in window and asks for my password again. I "
        "enter it and it works for a while, then the prompt comes back.",
        Category.SOFTWARE,
        Priority.P3,
        SARA,
        age=hours(18) + minutes(30),
        steps=(
            Assign(hours(1), AGENT),
            Reply(
                hours(1) + minutes(10),
                AGENT,
                "Hi Sara, does the prompt also appear in Outlook on the web "
                "(outlook.office.com), or only in the desktop app?",
            ),
            Reply(hours(3), SARA, "Only in the desktop app. The web version works fine."),
            Note(
                hours(3) + minutes(20),
                "Probably a stale token after the MFA rollout. Plan: clear the Office identity "
                "cache and the stored credentials with her on a call.",
            ),
            Reply(
                hours(3) + minutes(25),
                AGENT,
                "Thanks. Could we take 15 minutes on Teams to clear out the old sign-in tokens "
                "together? I've sent you an invite.",
            ),
        ),
    ),
    DemoTicket(
        "Docking station doesn't detect my external monitors",
        "When I connect the laptop to the dock neither of my two monitors gets a signal. The "
        "laptop charges through the dock, and the keyboard and mouse on it work.",
        Category.HARDWARE,
        Priority.P4,
        LUKAS,
        age=hours(58),
        steps=(
            Assign(hours(4), AGENT),
            Link(hours(4), "lukas-dock"),
            Reply(
                hours(4) + minutes(10),
                AGENT,
                "Hi Lukas, could you try the other USB-C port on the laptop, and unplug the "
                "dock's power for 30 seconds? If that doesn't help I'll update the dock firmware "
                "remotely.",
            ),
            Reply(
                days(1) + hours(1),
                LUKAS,
                "Tried both, still nothing on either screen. The laptop still charges though.",
            ),
            Note(
                days(1) + hours(2),
                "Dock firmware is 1.0.80; 1.0.92 fixes DisplayPort MST with Intel Iris Xe. "
                "Scheduling the update for his next office day.",
            ),
        ),
    ),
    # --- Open: on track --------------------------------------------------------------------
    DemoTicket(
        "Laptop stuck on the BitLocker recovery screen",
        "This morning my laptop asks for a BitLocker recovery key when it starts and I can't get "
        "past it. I have the month-end close today, so I need it working as soon as possible.",
        Category.HARDWARE,
        Priority.P2,
        JOHAN,
        age=hours(1) + minutes(15),
        steps=(
            Assign(minutes(8), AGENT),
            Link(minutes(9), "johan-laptop"),
            Reply(
                minutes(15),
                AGENT,
                "Hi Johan, this usually happens after a firmware update. I've sent the recovery "
                "key to your phone by SMS: enter it on the blue screen and Windows will start "
                "normally. Let me know if it asks again after a restart.",
            ),
            Note(
                minutes(20),
                "Recovery key retrieved from Entra ID. HP pushed a BIOS update last night, which "
                "changes the TPM measurements. Will suspend and resume BitLocker once he's in.",
            ),
        ),
    ),
    DemoTicket(
        "New starter: accounts and laptop for Lina Ek (starts Monday)",
        "Lina Ek joins HR as a recruitment coordinator on Monday. She needs a laptop, an email "
        "account, Teams, and access to Workday and the HR shared drive.",
        Category.ACCESS,
        Priority.P3,
        AMIRA,
        age=hours(6),
        steps=(
            Assign(minutes(30), ADMIN, by=ADMIN),
            Link(minutes(40), "spare-laptop", by=ADMIN),
            Note(
                minutes(45),
                "Spare ThinkPad reserved for Lina. Accounts: AD + Microsoft 365 E3, groups "
                "HR-All and HR-Recruitment, Workday via SSO.",
                by=ADMIN,
            ),
            Reply(
                minutes(50),
                ADMIN,
                "Hi Amira, a laptop is reserved and the accounts will be ready on Friday "
                "afternoon. Who will be Lina's manager, so we can set up her approvals?",
            ),
            Reply(hours(1) + minutes(30), AMIRA, "Her manager is Karin Holm. Thanks Ada!"),
        ),
    ),
    DemoTicket(
        "Floor 2 printer jams on every double-sided print",
        "The printer on floor 2 jams every time I print double-sided. Single-sided pages come out "
        "fine. Others on the floor have the same problem.",
        Category.HARDWARE,
        Priority.P3,
        SARA,
        age=hours(5),
        steps=(
            Assign(minutes(25), AGENT),
            Link(minutes(26), "printer-floor2"),
            Reply(
                minutes(30),
                AGENT,
                "Thanks Sara, I'll take a look this morning. Until then single-sided printing "
                "works, or you can use the printer by the kitchen on floor 3.",
            ),
            Note(
                hours(1) + minutes(40),
                "Duplex pickup roller is worn. Covered by the service contract: HP engineer "
                "booked, case 5079-112. Taking the printer out of service until then.",
            ),
            AssetStatusChange(
                hours(1) + minutes(45), AssetStatus.IN_REPAIR, "printer-floor2", AGENT
            ),
            Reply(
                hours(1) + minutes(50),
                AGENT,
                "The duplex unit needs a new part and an HP engineer is booked. The printer is "
                "marked as in repair until it's fixed.",
            ),
        ),
    ),
    DemoTicket(
        "Admin rights to install Python packages",
        "I'd like local admin rights so I can install Python and a few packages for automating "
        "our finance reports.",
        Category.ACCESS,
        Priority.P4,
        JOHAN,
        age=hours(1) + minutes(30),
        steps=(
            Assign(minutes(30), AGENT),
            Note(
                minutes(35),
                "Local admin isn't granted on standard laptops. Offer Python from Company Portal "
                "(user-scope pip installs) or a developer VM.",
            ),
            Reply(
                minutes(45),
                AGENT,
                "Hi Johan, we can't give local admin rights on standard laptops, but there are "
                "two options: Python 3.12 from Company Portal, which installs packages into your "
                "own profile without admin rights, or a developer VM if you need system-level "
                "tools. Which suits you better?",
            ),
        ),
    ),
    # --- Open: new and unassigned --------------------------------------------------------
    DemoTicket(
        "Wi-Fi keeps dropping in meeting room Saturnus",
        "Reported by phone: laptops in Saturnus lose the Wi-Fi every few minutes during meetings. "
        "Other rooms on the same floor are fine.",
        Category.NETWORK,
        Priority.P3,
        ERIK,
        age=hours(3),
        logged_by=AGENT,
        steps=(Link(minutes(1), "ap-saturnus"),),
    ),
    DemoTicket(
        "Access to the Sales Performance workspace in Power BI",
        "I've joined the sales operations team and need view access to the 'Sales Performance' "
        "workspace in Power BI. My manager Anders Wik has approved it.",
        Category.ACCESS,
        Priority.P4,
        LUKAS,
        age=minutes(20),
    ),
    # --- Resolved, waiting for the requester to confirm ---------------------------------
    DemoTicket(
        "Second monitor for my home office",
        "I work from home three days a week and would like a second monitor for my home desk. "
        "My manager has approved it.",
        Category.HARDWARE,
        Priority.P4,
        GRACE,
        age=days(4),
        steps=(
            Assign(hours(3), AGENT),
            Reply(
                hours(3) + minutes(5),
                AGENT,
                "We have a Dell 27-inch in stock. Would you like it delivered, or will you pick "
                "it up at the service desk?",
            ),
            Reply(hours(5), GRACE, "Picking it up works, thanks!"),
            AssetAssign(days(1) + hours(2), GRACE, "grace-monitor", AGENT),
            Link(days(1) + hours(2), "grace-monitor"),
            Reply(
                days(1) + hours(2) + minutes(5),
                AGENT,
                "The monitor is ready at the service desk with a USB-C cable, and it now shows "
                "under My equipment.",
            ),
            Status(days(1) + hours(2) + minutes(10), TicketStatus.RESOLVED),
        ),
    ),
    DemoTicket(
        "Excel crashes when opening large CSV exports",
        "Excel closes without an error when I open the monthly ledger export from the finance "
        "system. Smaller files open fine.",
        Category.SOFTWARE,
        Priority.P3,
        JOHAN,
        age=days(2),
        steps=(
            Assign(hours(1), AGENT),
            Reply(
                hours(1) + minutes(30),
                AGENT,
                "Hi Johan, roughly how big is the file? Does Excel crash right away or after "
                "loading for a while?",
            ),
            Reply(
                hours(3),
                JOHAN,
                "About 480 MB. It loads for a minute and then Excel just closes.",
            ),
            Note(
                hours(20),
                "32-bit Office on his laptop because of a legacy add-in, so Excel tops out "
                "around 2 GB of memory. The add-in has a 64-bit build: moving him to 64-bit.",
            ),
            Reply(
                hours(30),
                AGENT,
                "You're now on the 64-bit version of Office, which can use all of the laptop's "
                "memory. The ledger export opens in about 40 seconds in my test, please give it "
                "a try.",
            ),
            Status(hours(30) + minutes(5), TicketStatus.RESOLVED),
        ),
    ),
    # --- Closed ---------------------------------------------------------------------------
    DemoTicket(
        "Cracked phone screen",
        "I dropped my work phone and the screen is cracked across the top. It still works but "
        "the touch screen doesn't respond near the crack.",
        Category.HARDWARE,
        Priority.P3,
        AMIRA,
        age=days(4),
        steps=(
            Assign(hours(1), ADMIN, by=ADMIN),
            Link(hours(1), "amira-phone", by=ADMIN),
            Reply(
                hours(1) + minutes(10),
                ADMIN,
                "Sorry to hear that! Bring the phone to the service desk and you'll get a "
                "replacement the same day. Please back up your chats first.",
            ),
            AssetStatusChange(hours(5), AssetStatus.IN_REPAIR, "amira-phone", ADMIN),
            Link(hours(5) + minutes(5), "spare-phone", by=ADMIN),
            AssetAssign(hours(5) + minutes(5), AMIRA, "spare-phone", ADMIN),
            Reply(
                hours(5) + minutes(10),
                ADMIN,
                "Your replacement iPhone is set up and assigned to you. The cracked phone has "
                "gone to the repair partner and will come back as a spare.",
            ),
            Status(hours(5) + minutes(15), TicketStatus.RESOLVED, by=ADMIN),
            Status(days(1), TicketStatus.CLOSED, by=AMIRA),
        ),
    ),
    DemoTicket(
        "Suspicious 'Invoice overdue' email with an attachment",
        "I got an email saying an invoice is overdue, with a zip attachment. I don't recognise "
        "the sender and haven't opened it.",
        Category.OTHER,
        Priority.P2,
        PRIYA,
        age=days(5),
        steps=(
            Assign(minutes(10), AGENT),
            Reply(
                minutes(15),
                AGENT,
                "Thank you for reporting it rather than opening it! Please leave the attachment "
                "alone; I'm removing the email from all mailboxes now.",
            ),
            Note(
                minutes(40),
                "Lookalike sender domain. Purged from 37 mailboxes, blocked the domain and the "
                "attachment hash. URL logs show nobody clicked.",
            ),
            Status(minutes(45), TicketStatus.RESOLVED),
            Status(hours(3), TicketStatus.CLOSED, by=PRIYA),
        ),
    ),
    DemoTicket(
        "Install Adobe Acrobat Pro",
        "I need Acrobat Pro to edit and sign PDF contracts. Reader isn't enough.",
        Category.SOFTWARE,
        Priority.P4,
        MATEO,
        age=days(6),
        steps=(
            Assign(hours(5), AGENT),
            Reply(
                hours(5) + minutes(10),
                AGENT,
                "Licence approved. Acrobat Pro is now available in Company Portal: click "
                "Install and it'll be ready in a few minutes.",
            ),
            Status(hours(5) + minutes(15), TicketStatus.RESOLVED),
            Reply(days(1), MATEO, "Installed and working, thanks."),
            Status(days(1) + minutes(1), TicketStatus.CLOSED, by=MATEO),
        ),
    ),
    DemoTicket(
        "Password reset for SAP",
        "I've been locked out of SAP after too many attempts. I need to approve purchase orders "
        "before noon.",
        Category.ACCESS,
        Priority.P2,
        SARA,
        age=days(8),
        steps=(
            Assign(minutes(5), AGENT),
            Reply(
                minutes(12),
                AGENT,
                "Done: your account is unlocked and a temporary password has been sent to you by "
                "SMS. You'll be asked to change it when you sign in.",
            ),
            Status(minutes(13), TicketStatus.RESOLVED),
            Status(minutes(40), TicketStatus.CLOSED, by=SARA),
        ),
    ),
    DemoTicket(
        "Can't open the Finance shared folder after changing my password",
        "Since I changed my password this morning I get 'access denied' on the Finance shared "
        "folder. Everything else works.",
        Category.ACCESS,
        Priority.P3,
        GRACE,
        age=days(9),
        steps=(
            Assign(minutes(20), AGENT),
            Reply(
                minutes(25),
                AGENT,
                "Your laptop still had the old password saved for the file server. I've cleared "
                "it remotely: please sign out and back in, then open the Finance folder again.",
            ),
            Reply(hours(1), GRACE, "That fixed it, thank you!"),
            Status(hours(1) + minutes(5), TicketStatus.RESOLVED),
            Status(hours(1) + minutes(20), TicketStatus.CLOSED, by=GRACE),
        ),
    ),
    DemoTicket(
        "Payroll system unreachable from the Finance floor",
        "Nobody in Finance can reach the payroll system this morning; it times out in the "
        "browser. Salaries have to be approved today.",
        Category.NETWORK,
        Priority.P1,
        JOHAN,
        age=days(7),
        steps=(
            Assign(minutes(5), AGENT),
            Reply(
                minutes(10),
                AGENT,
                "We're on it. Several people in Finance report the same, so we're handling it as "
                "a major incident.",
            ),
            Note(
                minutes(40),
                "Cause: last night's firewall change (CHG-2291) removed the rule from the Finance "
                "VLAN to the payroll provider. Network team is restoring it.",
            ),
            Reply(
                hours(1) + minutes(20),
                AGENT,
                "Access to the payroll system is restored. A firewall change last night caused "
                "it and has been rolled back. Sorry for the disruption!",
            ),
            Status(hours(1) + minutes(25), TicketStatus.RESOLVED),
            Status(hours(3), TicketStatus.CLOSED, by=JOHAN),
        ),
    ),
]
