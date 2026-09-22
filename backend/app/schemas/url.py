from pydantic import BaseModel, HttpUrl


class URLRequest(BaseModel):
    url: HttpUrl


class URLSearchRequest(BaseModel):
    query: str


class URLSearchResult(BaseModel):
    title: str
    url: str
    snippet: str