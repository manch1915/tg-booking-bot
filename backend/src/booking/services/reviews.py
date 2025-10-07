from sqlalchemy.ext.asyncio import AsyncSession

from booking.domain.enums import BookingStatus, NotificationKind
from booking.infra.db.models import Booking, Review
from booking.services.clock import Clock
from booking.services.errors import InvalidStateError, PolicyError
from booking.services.notifications import NotificationScheduler


class ReviewService:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.notifications = NotificationScheduler(session, clock)

    async def leave(self, booking: Booking, rating: int, comment: str = "") -> Review:
        if not 1 <= rating <= 5:
            raise PolicyError("Rating must be between 1 and 5")
        if booking.status is not BookingStatus.COMPLETED:
            raise InvalidStateError("You can rate a visit after it took place")
        if booking.review is not None:
            booking.review.rating = rating
            if comment:
                booking.review.comment = comment.strip()[:1000]
            return booking.review
        review = Review(
            booking_id=booking.id,
            client_id=booking.client_id,
            master_id=booking.master_id,
            rating=rating,
            comment=comment.strip()[:1000],
        )
        self.session.add(review)
        await self.notifications.cancel_pending(booking.id, [NotificationKind.REVIEW_REQUEST])
        await self.session.flush()
        return review
