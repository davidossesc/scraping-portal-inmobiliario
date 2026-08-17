"""Configuración del WebDriver. Local (Windows) usa Edge; CI (GitHub Actions, Ubuntu) usa Chrome."""

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def crear_driver(navegador: str = "edge", headless: bool = False):
    if navegador == "chrome":
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        options = Options()
        options.add_argument(f"--user-agent={USER_AGENT}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if headless:
            options.add_argument("--headless=new")
        return webdriver.Chrome(options=options)

    if navegador == "edge":
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options

        options = Options()
        options.add_argument(f"--user-agent={USER_AGENT}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        if headless:
            options.add_argument("--headless=new")
        return webdriver.Edge(options=options)

    raise ValueError(f"Navegador no soportado: {navegador!r} (usa 'edge' o 'chrome')")
