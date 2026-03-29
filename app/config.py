from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SurakshaPay API"
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    database_url: str = "sqlite:///./surakshapay.db"

    openweather_api_key: str = ""
    waqi_api_token: str = ""

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    default_city_lat: float = 13.0827
    default_city_lon: float = 80.2707
    demo_zone_id: str = "chennai-t-nagar"


settings = Settings()
