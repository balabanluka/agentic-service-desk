"""Explicit, repeatable bootstrap of mutable tickets from the synthetic seed."""

from service_desk.config import Settings
from service_desk.data.repository import BusinessRepository
from service_desk.ticketing.repository import TicketRepository


def main() -> None:
    settings = Settings()
    if settings.database_url is None:
        raise SystemExit("DATABASE_URL must be configured before seeding tickets")
    seed = BusinessRepository.from_default_seed()
    repository = TicketRepository.connect(settings.database_url.get_secret_value())
    try:
        inserted = repository.seed(seed.seed_data.tickets)
    finally:
        repository.close()
    print(f"Ticket seed complete: inserted={inserted}, seen={len(seed.seed_data.tickets)}")


if __name__ == "__main__":
    main()
