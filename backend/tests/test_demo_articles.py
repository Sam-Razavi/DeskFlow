from app.demo_articles import DEMO_ARTICLES
from app.models.article import ArticleStatus
from app.schemas.article import ArticleCreate


def test_demo_articles_are_valid_and_unique():
    titles = [a.title for a in DEMO_ARTICLES]
    assert len(titles) == len(set(titles)), "the seed matches existing articles by title"
    for article in DEMO_ARTICLES:
        # The same rules the API applies to anything staff write.
        ArticleCreate(title=article.title, body=article.body, category=article.category)


def test_demo_set_has_published_articles_and_a_draft_to_show_the_workflow():
    statuses = {a.status for a in DEMO_ARTICLES}
    assert statuses == {ArticleStatus.PUBLISHED, ArticleStatus.DRAFT}
