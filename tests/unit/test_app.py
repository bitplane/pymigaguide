import pytest
from textual.widgets import Markdown

from pymigaguide.app import GuideApp


@pytest.fixture
def sample_guide_path(tmp_path):
    content = """
@DATABASE Sample
@NODE MAIN "Welcome"
@{b}AmigaGuide demo@{ub}

See @{"Other node" LINK "Other"}.
@ENDNODE

@NODE Other "Second Page"
This is the @{i}other@{ui} node. @{"Back to main" LINK "MAIN"}
@ENDNODE
"""
    guide_file = tmp_path / "sample.guide"
    guide_file.write_text(content)
    return guide_file


@pytest.mark.asyncio
async def test_guide_app_loads_and_renders_main_node(sample_guide_path):
    app = GuideApp(guide_path=str(sample_guide_path))
    async with app.run_test() as driver:
        markdown_widget = driver.app.query_one(Markdown)
        assert "# Welcome" in markdown_widget._markdown
        assert "**AmigaGuide demo**" in markdown_widget._markdown
        assert "[Other node](#other)" in markdown_widget._markdown


@pytest.mark.asyncio
async def test_guide_app_navigates_to_other_node(sample_guide_path):
    app = GuideApp(guide_path=str(sample_guide_path))
    async with app.run_test() as driver:

        async def navigate_and_assert():
            await driver.app.query_one("GuideView").goto(file=None, node="Other", line=None)
            markdown_widget = driver.app.query_one(Markdown)
            assert "# Second Page" in markdown_widget._markdown
            assert "*other*" in markdown_widget._markdown
            assert "[Back to main](MAIN)" in markdown_widget._markdown

        driver.app.call_after_refresh(navigate_and_assert)
