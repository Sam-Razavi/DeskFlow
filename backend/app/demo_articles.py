"""Sample knowledge-base articles for the demo deployment (see app.seed)."""

from typing import NamedTuple

from app.models.article import ArticleStatus
from app.models.ticket import Category


class DemoArticle(NamedTuple):
    title: str
    category: Category
    status: ArticleStatus
    body: str


P = ArticleStatus.PUBLISHED

# Newest first: the seed spaces their publish dates out in this order.
DEMO_ARTICLES: list[DemoArticle] = [
    DemoArticle(
        "Fix a VPN that keeps disconnecting",
        Category.NETWORK,
        P,
        """If the VPN drops every few minutes, work through these steps in order. Most cases are
solved by the first three.

## Quick fixes

1. **Quit and reopen the VPN client.** Closing the window is not enough; use *Quit* from the tray.
2. **Switch from Wi-Fi to a cable** if you can. Weak Wi-Fi is the most common cause of drops.
3. **Restart your computer.** This clears stale network adapters left over from a previous session.

## Still dropping?

Flush your DNS cache and renew your address.

```powershell
ipconfig /flushdns
ipconfig /release
ipconfig /renew
```

Then check which error you see:

| Message | What it means | What to do |
|---|---|---|
| `Connection timed out` | The gateway is unreachable | Try another network, such as a phone hotspot |
| `Authentication failed` | Wrong password or expired MFA | Reset your password, then sign in again |
| `Tunnel closed unexpectedly` | A firewall is interrupting the link | Open a ticket and tell us where you work from |

> If you are on a hotel or café network, a captive portal may be blocking the tunnel. Open a
> browser, accept the terms, then reconnect.

When you open a ticket, include the **time of the last drop** and the **error message**. It lets us
find your session in the gateway logs.
""",
    ),
    DemoArticle(
        "Set up multi-factor authentication",
        Category.ACCESS,
        P,
        """Multi-factor authentication (MFA) protects your account even if your password leaks.
You need an authenticator app on your phone.

## Set it up

1. Install **Microsoft Authenticator** or any app that supports one-time codes.
2. Sign in to the self-service portal and open **Security**.
3. Choose **Add method**, then **Authenticator app**.
4. Scan the QR code, then type the six-digit code to confirm.

## Lost your phone?

Do not panic. Open a ticket with the category **Access** and we will verify who you are and reset
your method. Until then you can still use your backup codes.

- Keep your backup codes somewhere safe, but **not** on the same phone.
- Never share a code with anyone. We will never ask you for one.
""",
    ),
    DemoArticle(
        "How to reset your password",
        Category.ACCESS,
        P,
        """You can reset your own password without contacting us.

1. Go to the self-service portal and choose **Forgot password**.
2. Enter your work email address.
3. Open the email we send you and follow the link. It expires after **30 minutes**.
4. Choose a new password.

## Password rules

- At least 12 characters
- Not one of your last 10 passwords
- Not a word that appears in the dictionary on its own

A passphrase of four unrelated words is easier to remember than a complicated short password and
much harder to guess.

## The email never arrived

Check your spam folder first. If it is not there after five minutes, open a ticket and we will
reset it for you.
""",
    ),
    DemoArticle(
        "Add a network printer",
        Category.HARDWARE,
        P,
        """Printers on each floor are shared. You only need to add one the first time.

## Windows

1. Open **Settings**, then **Bluetooth & devices**, then **Printers & scanners**.
2. Choose **Add device** and wait for the list to fill.
3. Pick the printer for your floor, for example `PRN-FLOOR3-A`, and select **Add device**.

## macOS

1. Open **System Settings**, then **Printers & Scanners**, and click **+**.
2. Choose the **IP** tab and enter the printer address from the label on the machine.
3. Set *Use* to **Secure AirPrint** and click **Add**.

## Printing works but scanning to email does not

Scanning to email is a separate setup. Open a ticket and tell us your email address and which
printer you use.

## Common problems

- **The job disappears.** Open the print queue and cancel stuck jobs, then try again.
- **Printer shows as offline.** Check the display for a paper jam or an empty toner message.
""",
    ),
    DemoArticle(
        "My laptop is running slowly",
        Category.HARDWARE,
        P,
        """A slow laptop is usually caused by too many programs starting with Windows, a full disk or
a pending update. Try these before opening a ticket.

1. **Restart.** A laptop that has been asleep for weeks builds up background tasks.
2. **Check what is using your resources.** Press `Ctrl` + `Shift` + `Esc` and open the **Processes**
   tab. Sort by *CPU* or *Memory* and close anything you do not recognise.
3. **Free up disk space.** Less than 10% free space makes everything slower. Empty the recycle bin
   and remove large downloads.
4. **Install pending updates.** Updates that are waiting often run in the background at the worst
   moment.

If your laptop is still slow after all this, or the fan is always loud, open a ticket. It may need
a hardware check, and we may replace it if it is more than four years old.
""",
    ),
    DemoArticle(
        "Connect to the office Wi-Fi",
        Category.NETWORK,
        P,
        """Two networks are available in the office:

| Network | Use it for | Sign in with |
|---|---|---|
| `Corp` | Your work laptop | Your work email and password |
| `Guest` | Visitors and personal phones | The code on the reception screen |

## Work laptop

Select **Corp** and sign in. The first time, accept the certificate when asked. If you changed your
password recently, forget the network and add it again.

## Visitors

Select **Guest** and open a browser. Enter the code shown at reception. Guest access ends after
**24 hours** and cannot reach internal systems.
""",
    ),
    DemoArticle(
        "Request software to be installed",
        Category.SOFTWARE,
        P,
        """You cannot install software yourself on a work laptop. We review each request for licensing
and security first.

## Before you ask

- Check the **Software Center** on your laptop. Many tools are already approved and install in a
  few clicks.
- Ask your manager whether the licence cost is approved.

## How to ask

Open a ticket with the category **Software** and include the name of the program, why you need it
and how long you need it for. Requests for approved software are usually done the same day.
""",
    ),
    DemoArticle(
        "New starter equipment checklist",
        Category.HARDWARE,
        ArticleStatus.DRAFT,
        """_Draft: still to be reviewed by the service desk._

- Laptop and charger
- Monitor, keyboard and mouse
- Phone and headset
- Building pass
""",
    ),
]
