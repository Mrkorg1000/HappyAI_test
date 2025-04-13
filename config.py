from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    OPENAI_API_KEY: str

    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    
    AMPLITUDE_API_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8")

    @property
    def database_url(self) -> str:
        user = self.POSTGRES_USER
        password = self.POSTGRES_PASSWORD
        host = self.POSTGRES_HOST
        port = self.POSTGRES_PORT
        db = self.POSTGRES_DB
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

settings = Settings()
