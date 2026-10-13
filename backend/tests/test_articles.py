import pytest

from app.services.articles import EXCERPT_LENGTH, HIGHLIGHT_END, HIGHLIGHT_START, excerpt

VPN = {
    "title": "Fixing a VPN that keeps disconnecting",
    "body": (
        "If the VPN drops every few minutes, restart the client and switch from Wi-Fi to a cable."
    ),
    "category": "network",
}
PASSWORD = {
    "title": "How to reset your password",
    "body": "Open the self-service portal, choose **Forgot password** and follow the emailed link.",
    "category": "access",
}
PRINTER = {
    "title": "Printer setup",
    "body": "Add the floor printer from Settings. Scanning to email needs a separate step.",
    "category": "hardware",
}


async def create(client, headers, publish=False, **overrides):
    res = await client.post("/api/articles", json={**PASSWORD, **overrides}, headers=headers)
    assert res.status_code == 201, res.text
    article = res.json()
    if publish:
        res = await client.post(f"/api/articles/{article['id']}/publish", headers=headers)
        assert res.status_code == 200, res.text
        article = res.json()
    return article


async def search(client, headers, q, **params):
    res = await client.get("/api/articles", params={"q": q, **params}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def titles(page):
    return [a["title"] for a in page["items"]]


# --- creating and editing ------------------------------------------------------------------------


async def test_staff_create_a_draft_owned_by_them(client, people):
    agent, headers = people["agent"]
    article = await create(client, headers)
    assert article["status"] == "draft"
    assert article["published_at"] is None
    assert article["author"]["id"] == agent.id


async def test_only_staff_can_write(client, people):
    _, req_headers = people["req"]
    assert (
        await client.post("/api/articles", json=PASSWORD, headers=req_headers)
    ).status_code == 403
    assert (await client.post("/api/articles", json=PASSWORD)).status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [{"title": "ab"}, {"title": "   "}, {"body": ""}, {"body": "   "}, {"category": "weather"}],
)
async def test_create_validates_input(client, people, overrides):
    _, headers = people["agent"]
    res = await client.post("/api/articles", json={**PASSWORD, **overrides}, headers=headers)
    assert res.status_code == 422


async def test_text_is_trimmed(client, people):
    _, headers = people["agent"]
    article = await create(client, headers, title="  Padded title  ", body="\n  Some text  \n")
    assert article["title"] == "Padded title"
    assert article["body"] == "Some text"


async def test_update_changes_fields_and_only_staff_may(client, people):
    _, req_headers = people["req"]
    _, headers = people["agent"]
    article = await create(client, headers, publish=True)
    url = f"/api/articles/{article['id']}"

    res = await client.patch(
        url, json={"title": "Reset a forgotten password", "category": "software"}, headers=headers
    )
    body = res.json()
    assert body["title"] == "Reset a forgotten password"
    assert body["category"] == "software"
    assert body["body"] == PASSWORD["body"]  # untouched
    assert body["status"] == "published"  # editing never unpublishes

    assert (
        await client.patch(url, json={"title": "Hacked title"}, headers=req_headers)
    ).status_code == 403


# --- publishing and visibility -------------------------------------------------------------------


async def test_publish_and_unpublish(client, people):
    _, headers = people["agent"]
    article = await create(client, headers)
    url = f"/api/articles/{article['id']}"

    published = (await client.post(f"{url}/publish", headers=headers)).json()
    assert published["status"] == "published"
    assert published["published_at"] is not None
    assert (await client.post(f"{url}/publish", headers=headers)).status_code == 409

    draft = (await client.post(f"{url}/unpublish", headers=headers)).json()
    assert draft["status"] == "draft"
    assert draft["published_at"] is None
    assert (await client.post(f"{url}/unpublish", headers=headers)).status_code == 409


async def test_requesters_cannot_publish(client, people):
    _, req_headers = people["req"]
    _, headers = people["agent"]
    article = await create(client, headers)
    res = await client.post(f"/api/articles/{article['id']}/publish", headers=req_headers)
    assert res.status_code == 403


async def test_drafts_are_invisible_to_requesters_everywhere(client, people):
    _, req_headers = people["req"]
    _, headers = people["agent"]
    draft = await create(client, headers, title="Unfinished draft")
    live = await create(client, headers, title="Live article", publish=True)

    assert (
        await client.get(f"/api/articles/{draft['id']}", headers=req_headers)
    ).status_code == 404
    assert (await client.get(f"/api/articles/{live['id']}", headers=req_headers)).status_code == 200

    # Not even by asking for them, or by searching for their words.
    for params in ({}, {"status": "draft"}, {"q": "draft"}):
        page = (await client.get("/api/articles", params=params, headers=req_headers)).json()
        assert "Unfinished draft" not in titles(page), params
    suggested = await client.get(
        "/api/articles/suggest", params={"q": "unfinished"}, headers=req_headers
    )
    assert suggested.json() == []


async def test_staff_see_drafts_and_can_filter_by_status(client, people):
    _, headers = people["agent"]
    await create(client, headers, title="Unfinished draft")
    await create(client, headers, title="Live article", publish=True)

    assert (await client.get("/api/articles", headers=headers)).json()["total"] == 2
    drafts = (await client.get("/api/articles?status=draft", headers=headers)).json()
    assert titles(drafts) == ["Unfinished draft"]
    live = (await client.get("/api/articles?status=published", headers=headers)).json()
    assert titles(live) == ["Live article"]


async def test_list_filters_by_category_and_paginates_newest_first(client, people):
    _, headers = people["agent"]
    await create(client, headers, publish=True, **VPN)
    await create(client, headers, publish=True, **PASSWORD)
    await create(client, headers, publish=True, **PRINTER)

    page = (await client.get("/api/articles", headers=headers)).json()
    assert titles(page) == [
        PRINTER["title"],
        PASSWORD["title"],
        VPN["title"],
    ]  # newest published first

    network = (await client.get("/api/articles?category=network", headers=headers)).json()
    assert titles(network) == [VPN["title"]]

    second = (await client.get("/api/articles?limit=2&offset=2", headers=headers)).json()
    assert second["total"] == 3
    assert titles(second) == [VPN["title"]]


async def test_list_items_do_not_carry_the_full_body(client, people):
    _, headers = people["agent"]
    await create(client, headers, publish=True)
    item = (await client.get("/api/articles", headers=headers)).json()["items"][0]
    assert "body" not in item
    assert item["snippet"]


# --- search --------------------------------------------------------------------------------------


@pytest.fixture
async def library(client, people):
    _, headers = people["agent"]
    for article in (VPN, PASSWORD, PRINTER):
        await create(client, headers, publish=True, **article)
    return headers


async def test_search_finds_articles_by_body_text(client, library):
    assert titles(await search(client, library, "cable")) == [VPN["title"]]


async def test_search_ranks_title_matches_above_body_matches(client, people):
    _, headers = people["agent"]
    await create(
        client,
        headers,
        publish=True,
        title="Office parties",
        body="Book the room. Printer jams are not our problem.",
    )
    await create(
        client,
        headers,
        publish=True,
        title="Printer troubleshooting",
        body="Check paper and toner.",
    )
    assert titles(await search(client, headers, "printer"))[0] == "Printer troubleshooting"


async def test_search_understands_word_forms_and_case(client, library):
    # Stemming: "printers" finds "printer", "disconnect" finds "disconnecting".
    assert PRINTER["title"] in titles(await search(client, library, "printers"))
    assert VPN["title"] in titles(await search(client, library, "DISCONNECT"))


async def test_search_requires_every_word_and_supports_phrases_and_exclusions(client, library):
    assert titles(await search(client, library, "vpn cable")) == [VPN["title"]]
    assert (await search(client, library, "vpn printer"))[
        "total"
    ] == 0  # no single article has both
    assert titles(await search(client, library, '"reset your password"')) == [PASSWORD["title"]]
    assert (await search(client, library, '"your reset password"'))["total"] == 0  # order matters
    assert PRINTER["title"] not in titles(await search(client, library, "email -scanning"))


async def test_search_with_no_match_returns_an_empty_page(client, library):
    page = await search(client, library, "xylophone")
    assert page == {"items": [], "total": 0}


async def test_search_total_counts_all_matches_not_just_the_page(client, library):
    page = await search(client, library, "the", limit=1)  # a stop word matches nothing...
    assert page["total"] == 0
    page = await search(client, library, "email", limit=1)  # ...but real words count every hit
    assert page["total"] == 2 and len(page["items"]) == 1


@pytest.mark.parametrize(
    "hostile",
    [
        "'; DROP TABLE articles; --",
        "vpn & | ! ( ) : * <-> <2>",
        '"unterminated phrase',
        "\\",
        "a" * 200,
        "%_",
        "⟦⟧",
    ],
)
async def test_search_survives_hostile_input(client, library, hostile):
    res = await client.get("/api/articles", params={"q": hostile}, headers=library)
    assert res.status_code == 200
    # ...and the table is still there.
    assert (await client.get("/api/articles", headers=library)).json()["total"] == 3


async def test_search_ignores_a_blank_query(client, library):
    assert (await search(client, library, "   "))["total"] == 3


async def test_snippets_wrap_matches_in_highlight_markers_not_html(client, people):
    _, headers = people["agent"]
    await create(
        client,
        headers,
        publish=True,
        title="Markup test",
        body=(
            "Intro text. <b>Never trust</b> the router settings <script>alert(1)</script> "
            "before you continue."
        ),
    )
    item = (await search(client, headers, "router"))["items"][0]
    assert f"{HIGHLIGHT_START}router{HIGHLIGHT_END}" in item["snippet"]
    # Highlighting adds no markup of its own; any markup in the article is just text to the client.
    assert "<mark>" not in item["snippet"]


async def test_snippets_read_as_plain_sentences_not_markdown_source(client, people):
    _, headers = people["agent"]
    await create(
        client,
        headers,
        publish=True,
        title="Router guide",
        body=(
            "## Reset the router\n\n1. Hold the **reset button** for ten seconds.\n"
            "2. See [the vendor guide](https://vendor.example/guide) for the router lights.\n\n"
            "| Light | Meaning |\n|---|---|\n| Green | Router is fine |\n\n"
            "```\nrouter --factory-reset\n```\n\n> Note: the router restarts twice."
        ),
    )
    snippet = (await search(client, headers, "router"))["items"][0]["snippet"]
    assert f"{HIGHLIGHT_START}router{HIGHLIGHT_END}" in snippet
    for syntax in ("##", "**", "](", "https://", "```", "--factory-reset", "> ", "---", "|"):
        assert syntax not in snippet, syntax
    assert "the vendor guide" in snippet  # the link's label survives, its address does not
    assert "reset button ." not in snippet  # removed emphasis leaves no stray gap


async def test_filters_combine_with_search(client, library):
    assert titles(await search(client, library, "email", category="hardware")) == [PRINTER["title"]]
    assert (await search(client, library, "email", category="network"))["total"] == 0


# --- excerpts ------------------------------------------------------------------------------------


def test_excerpt_strips_markdown():
    text = (
        "# Heading\n\nUse **bold**, _italic_ and `code`. "
        "See [the guide](https://x.example/a).\n\n- item one\n- item two"
    )
    assert excerpt(text) == "Heading Use bold, italic and code. See the guide. item one item two"


def test_excerpt_drops_code_blocks_and_keeps_image_labels():
    text = "Intro\n\n```bash\nrm -rf /\n```\n\n![diagram of the network](net.png) after"
    assert excerpt(text) == "Intro diagram of the network after"


def test_excerpt_truncates_on_a_word_boundary():
    result = excerpt("word " * 100)
    assert result.endswith("…")
    assert len(result) <= EXCERPT_LENGTH + 1
    assert not result.rstrip("…").endswith("wor")  # never cuts a word in half


def test_short_excerpt_is_left_alone():
    assert excerpt("Short and sweet") == "Short and sweet"


async def test_listing_without_a_search_shows_plain_text_excerpts(client, people):
    _, headers = people["agent"]
    await create(
        client, headers, publish=True, body="# Steps\n\n1. Open **Settings**\n2. Click `Add`"
    )
    item = (await client.get("/api/articles", headers=headers)).json()["items"][0]
    assert item["snippet"] == "Steps 1. Open Settings 2. Click Add"


# --- suggestions ---------------------------------------------------------------------------------


async def test_suggestions_match_any_word_of_a_ticket_title(client, library, people):
    _, req_headers = people["req"]
    res = await client.get(
        "/api/articles/suggest", params={"q": "VPN keeps dropping again"}, headers=req_headers
    )
    assert [a["title"] for a in res.json()] == [VPN["title"]]


async def test_suggestions_rank_the_better_match_first(client, people):
    _, headers = people["agent"]
    await create(
        client, headers, publish=True, title="Wi-Fi basics", body="Connect to the office network."
    )
    await create(
        client,
        headers,
        publish=True,
        title="Wi-Fi password problems",
        body="Reset the Wi-Fi password and reconnect.",
    )
    res = await client.get("/api/articles/suggest", params={"q": "wifi password"}, headers=headers)
    assert res.json()[0]["title"] == "Wi-Fi password problems"


async def test_suggestions_only_come_from_published_articles(client, people):
    _, headers = people["agent"]
    await create(client, headers, title="Secret draft about VPN")
    res = await client.get("/api/articles/suggest", params={"q": "vpn"}, headers=headers)
    assert res.json() == []


async def test_suggestions_respect_the_limit_and_input_rules(client, people):
    _, headers = people["agent"]
    for n in range(4):
        await create(
            client, headers, publish=True, title=f"Printer guide {n}", body="Printer help."
        )
    assert (
        len(
            (
                await client.get(
                    "/api/articles/suggest", params={"q": "printer", "limit": 2}, headers=headers
                )
            ).json()
        )
        == 2
    )
    assert (
        await client.get("/api/articles/suggest", params={"q": "p"}, headers=headers)
    ).status_code == 422
    assert (
        await client.get(
            "/api/articles/suggest", params={"q": "printer", "limit": 11}, headers=headers
        )
    ).status_code == 422
    # Only stop words: nothing meaningful to look for, and not an error.
    assert (
        await client.get("/api/articles/suggest", params={"q": "the and of"}, headers=headers)
    ).json() == []
    assert (
        await client.get("/api/articles/suggest", params={"q": "'; drop table"}, headers=headers)
    ).status_code == 200


async def test_suggestions_need_a_login(client):
    assert (await client.get("/api/articles/suggest", params={"q": "vpn"})).status_code == 401


# --- history and deletion ------------------------------------------------------------------------


async def test_history_records_what_changed(client, people):
    _, headers = people["agent"]
    article = await create(client, headers)
    url = f"/api/articles/{article['id']}"
    await client.patch(url, json={"title": "A better title"}, headers=headers)
    await client.patch(url, json={"body": "Completely new text."}, headers=headers)
    await client.patch(url, json={"body": "Completely new text."}, headers=headers)  # a no-op
    await client.post(f"{url}/publish", headers=headers)
    await client.post(f"{url}/unpublish", headers=headers)

    entries = (await client.get(f"{url}/history", headers=headers)).json()
    assert [e["action"] for e in entries] == [
        "created",
        "updated",
        "updated",
        "published",
        "unpublished",
    ]
    assert entries[1]["changes"] == {"title": ["How to reset your password", "A better title"]}
    # Long bodies are not copied into the log; it only says the text changed.
    assert entries[2]["changes"] == {"body_changed": True}
    assert entries[3]["changes"] == {"status": ["draft", "published"]}


async def test_history_is_staff_only(client, people):
    _, req_headers = people["req"]
    _, headers = people["agent"]
    article = await create(client, headers, publish=True)
    res = await client.get(f"/api/articles/{article['id']}/history", headers=req_headers)
    assert res.status_code == 403


async def test_staff_can_discard_drafts_but_only_admins_delete_published_articles(client, people):
    _, agent_headers = people["agent"]
    _, admin_headers = people["admin"]
    draft = await create(client, agent_headers)
    live = await create(client, agent_headers, publish=True, title="Live article")

    assert (
        await client.delete(f"/api/articles/{draft['id']}", headers=agent_headers)
    ).status_code == 204
    assert (
        await client.get(f"/api/articles/{draft['id']}", headers=agent_headers)
    ).status_code == 404

    assert (
        await client.delete(f"/api/articles/{live['id']}", headers=agent_headers)
    ).status_code == 403
    assert (
        await client.get(f"/api/articles/{live['id']}", headers=agent_headers)
    ).status_code == 200
    assert (
        await client.delete(f"/api/articles/{live['id']}", headers=admin_headers)
    ).status_code == 204


async def test_requesters_cannot_delete(client, people):
    _, req_headers = people["req"]
    _, headers = people["agent"]
    article = await create(client, headers, publish=True)
    assert (
        await client.delete(f"/api/articles/{article['id']}", headers=req_headers)
    ).status_code == 403


async def test_a_deleted_article_stays_in_the_audit_log(client, people):
    _, agent_headers = people["agent"]
    _, admin_headers = people["admin"]
    article = await create(client, agent_headers, title="Short-lived article")
    await client.delete(f"/api/articles/{article['id']}", headers=agent_headers)

    log = (
        await client.get(
            f"/api/audit-logs?entity_type=article&entity_id={article['id']}", headers=admin_headers
        )
    ).json()
    assert [e["action"] for e in reversed(log["items"])] == ["created", "deleted"]
    assert log["items"][0]["changes"]["title"] == "Short-lived article"


async def test_unknown_article_is_a_404(client, people):
    _, headers = people["agent"]
    for method, path in (
        ("get", ""),
        ("patch", ""),
        ("delete", ""),
        ("post", "/publish"),
        ("get", "/history"),
    ):
        res = await client.request(
            method,
            f"/api/articles/99999{path}",
            headers=headers,
            **({"json": {}} if method == "patch" else {}),
        )
        assert res.status_code == 404, (method, path)


async def test_suggestions_prefer_articles_containing_every_word(client, people):
    _, headers = people["agent"]
    await create(client, headers, publish=True, **VPN)
    # Shares only the very common word "keeps" with the ticket title below.
    await create(
        client,
        headers,
        publish=True,
        title="Keeping your backup codes safe",
        body="Keeps these somewhere safe, but not on the same phone.",
    )
    res = await client.get(
        "/api/articles/suggest", params={"q": "VPN keeps dropping"}, headers=headers
    )
    assert [a["title"] for a in res.json()] == [VPN["title"]]


async def test_suggestions_fall_back_to_any_word_when_nothing_has_them_all(client, people):
    _, headers = people["agent"]
    await create(client, headers, publish=True, **VPN)
    # No article says "again", so the strict tier is empty and the lenient tier takes over.
    res = await client.get(
        "/api/articles/suggest", params={"q": "VPN keeps dropping again"}, headers=headers
    )
    assert [a["title"] for a in res.json()] == [VPN["title"]]


async def test_the_lenient_tier_drops_matches_far_weaker_than_the_best(client, people):
    _, headers = people["agent"]
    strong = await create(
        client,
        headers,
        publish=True,
        title="Outlook crashes on startup",
        body="Outlook crashes when opening. Repair Outlook from the control panel.",
    )
    await create(
        client,
        headers,
        publish=True,
        title="Opening a shared mailbox",
        body="A long guide about shared mailboxes. "
        + "Filler text about calendars. " * 40
        + "It does mention opening once.",
    )
    res = await client.get(
        "/api/articles/suggest",
        params={"q": "Outlook crashes opening attachments from Bob"},
        headers=headers,
    )
    assert [a["id"] for a in res.json()] == [strong["id"]]
