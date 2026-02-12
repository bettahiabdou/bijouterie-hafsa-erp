"""
AMANA Package Tracking Service

Scrapes tracking information from the AMANA/Barid tracking website.
Ported from the hafsa-tracking Next.js application.
"""

import re
import time
import logging
import requests
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class TimelineEvent:
    """A single timeline event from AMANA tracking"""
    number: str
    date: str
    time: str
    description: str
    location: str = ''


@dataclass
class TrackingResult:
    """Result from AMANA tracking lookup"""
    success: bool
    tracking_code: str
    status: str = 'pending'  # pending, in_transit, delivered
    product: str = ''
    weight: str = ''
    amount: str = ''  # COD amount
    current_position: str = ''
    destination: str = ''
    origin: str = ''
    deposit_date: str = ''
    delivery_date: str = ''
    timeline: List[TimelineEvent] = field(default_factory=list)
    error: str = ''
    fetched_at: str = ''


class AmanaTracker:
    """
    AMANA Package Tracking Service

    Scrapes the Barid Al-Maghrib tracking website to get package status.

    Usage:
        tracker = AmanaTracker()
        result = tracker.track("YOUR_TRACKING_CODE")
        if result.success:
            print(f"Status: {result.status}")
            print(f"Current Position: {result.current_position}")
    """

    BASE_URL = "https://bam-tracking.barid.ma/Tracking/Search"
    MAX_RETRIES = 3
    TIMEOUT = 10

    # HTML entity decode mapping
    HTML_ENTITIES = {
        '&#xE9;': 'é',
        '&#xE0;': 'à',
        '&#xC0;': 'À',
        '&#xE8;': 'è',
        '&#xE7;': 'ç',
        '&#x27;': "'",
        '&#39;': "'",
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '&quot;': '"',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'fr-FR,fr;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://bam-tracking.barid.ma/',
            'Origin': 'https://bam-tracking.barid.ma',
            'Connection': 'keep-alive',
            'X-Requested-With': 'XMLHttpRequest',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        })

    def _decode_html_entities(self, text: str) -> str:
        """Decode HTML entities in text"""
        for entity, char in self.HTML_ENTITIES.items():
            text = text.replace(entity, char)

        # Decode numeric entities: &#123;
        text = re.sub(
            r'&#(\d+);',
            lambda m: chr(int(m.group(1))),
            text
        )

        # Decode hex entities: &#x7B;
        text = re.sub(
            r'&#x([0-9A-Fa-f]+);',
            lambda m: chr(int(m.group(1), 16)),
            text
        )

        return text

    def _extract_text(self, html: str, class_name: str) -> Optional[str]:
        """
        Extract text content from HTML element with specific class.
        Matches the JS extractText function.
        """
        patterns = [
            rf'class="[^"]*{class_name}[^"]*"[^>]*>\s*([^<]+)',
            rf"class='[^']*{class_name}[^']*'[^>]*>\s*([^<]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match and match.group(1).strip() != '...':
                return match.group(1).strip()

        return None

    def _extract_timeline(self, html: str) -> List[TimelineEvent]:
        """
        Extract timeline events from HTML.
        Matches the JS timeline extraction logic.
        """
        timeline = []

        # Pattern matching the JS regex
        pattern = r'<li>[\s\S]*?class="bullet">(\d+)</div>[\s\S]*?class="container_date">([^<]+)</div>[\s\S]*?class="container_time">([^<]+)</div>[\s\S]*?<div[^>]*class="mt-3[^>]*>([^<]+(?:<b>[^<]*</b>)?[^<]*)</div>'

        matches = re.finditer(pattern, html, re.IGNORECASE)

        for match in matches:
            event_number = match.group(1).strip()
            event_date = match.group(2).strip()
            event_time = match.group(3).strip()
            description = match.group(4).strip()

            # Clean up description - remove HTML tags
            description = re.sub(r'<[^>]*>', ' ', description)
            description = re.sub(r'\s+', ' ', description).strip()

            # Decode HTML entities
            description = self._decode_html_entities(description)

            # Remove time from beginning of description if present
            if description.startswith(event_time):
                description = description[len(event_time):].strip()

            if description:
                timeline.append(TimelineEvent(
                    number=event_number,
                    date=event_date,
                    time=event_time,
                    description=description
                ))

        return timeline

    def _determine_status(self, delivery_date: str, timeline: List[TimelineEvent]) -> str:
        """
        Determine package status based on delivery date and timeline.
        Matches the JS status detection logic.
        """
        if delivery_date:
            return 'delivered'
        elif timeline:
            return 'in_transit'
        else:
            return 'pending'

    def _fetch_with_retry(self, tracking_code: str) -> requests.Response:
        """
        Fetch tracking data with exponential backoff retry.
        """
        timestamp = int(time.time() * 1000)
        url = f"{self.BASE_URL}?trackingCode={tracking_code}&_={timestamp}"

        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.debug(f"[Attempt {attempt}/{self.MAX_RETRIES}] Fetching from AMANA...")

                response = self.session.get(url, timeout=self.TIMEOUT)

                logger.debug(f"[Attempt {attempt}] Response status: {response.status_code}")
                return response

            except requests.RequestException as e:
                logger.warning(f"[Attempt {attempt}] Error: {e}")
                last_error = e

                if attempt < self.MAX_RETRIES:
                    wait_time = (2 ** (attempt - 1))  # Exponential backoff: 1s, 2s, 4s
                    logger.debug(f"[Attempt {attempt}] Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)

        raise last_error

    def track(self, tracking_code: str) -> TrackingResult:
        """
        Track a package by its tracking code.

        Args:
            tracking_code: The AMANA tracking code

        Returns:
            TrackingResult with package information
        """
        if not tracking_code:
            return TrackingResult(
                success=False,
                tracking_code='',
                error='Code de suivi requis'
            )

        tracking_code = tracking_code.strip().upper()

        logger.info(f"=== Tracking Request for: {tracking_code} ===")

        try:
            response = self._fetch_with_retry(tracking_code)

            if not response.ok:
                logger.error(f"API returned error status: {response.status_code}")
                return TrackingResult(
                    success=False,
                    tracking_code=tracking_code,
                    error=f'Erreur API: {response.status_code}'
                )

            data = response.json()

            # Check for successful response
            if not data.get('OperationSuccess') or not data.get('Html'):
                return TrackingResult(
                    success=False,
                    tracking_code=tracking_code,
                    error='Aucune information trouvée'
                )

            html = data['Html']

            # Extract package info
            product = self._extract_text(html, 'lblProductName') or ''
            weight = self._extract_text(html, 'lblWeight') or ''
            amount = self._extract_text(html, 'lblMttCrbt') or ''
            current_position = self._extract_text(html, 'lblCurrentPosition') or ''
            deposit_date = self._extract_text(html, 'lblDepositDate') or ''
            destination = self._extract_text(html, 'lblRecipient') or ''

            # Extract origin (special pattern)
            origin = ''
            origin_match = re.search(r'class="tooltip_depart"[^>]*>([^<]+)', html, re.IGNORECASE)
            if origin_match:
                origin = origin_match.group(1).strip()

            # Extract timeline
            timeline = self._extract_timeline(html)

            # Delivery date (not directly available, might be in timeline)
            delivery_date = ''

            # Determine status
            status = self._determine_status(delivery_date, timeline)

            logger.info(f"✓ Successfully fetched tracking data for {tracking_code}")

            return TrackingResult(
                success=True,
                tracking_code=tracking_code,
                status=status,
                product=product,
                weight=weight,
                amount=amount,
                current_position=current_position,
                destination=destination,
                origin=origin,
                deposit_date=deposit_date,
                delivery_date=delivery_date,
                timeline=timeline,
                fetched_at=timezone.now().isoformat()
            )

        except requests.RequestException as e:
            logger.error(f"Connection error: {e}")
            return TrackingResult(
                success=False,
                tracking_code=tracking_code,
                error='Le service AMANA est temporairement indisponible'
            )
        except ValueError as e:
            logger.error(f"JSON parse error: {e}")
            return TrackingResult(
                success=False,
                tracking_code=tracking_code,
                error='Erreur de parsing de la réponse'
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return TrackingResult(
                success=False,
                tracking_code=tracking_code,
                error=str(e)
            )

    def update_delivery(self, delivery) -> bool:
        """
        Update a Delivery model instance with fresh tracking data.

        Args:
            delivery: Delivery model instance

        Returns:
            True if updated successfully, False otherwise
        """
        from sales.models import Delivery, DeliveryTimelineEvent

        if not delivery.tracking_number:
            logger.warning(f"Delivery {delivery.reference} has no tracking number")
            return False

        result = self.track(delivery.tracking_number)

        if not result.success:
            logger.warning(f"Failed to track {delivery.tracking_number}: {result.error}")
            delivery.last_checked_at = timezone.now()
            delivery.save(update_fields=['last_checked_at'])
            return False

        # Update delivery fields
        delivery.status = result.status
        delivery.product = result.product
        delivery.weight = result.weight
        delivery.amount_cod = result.amount
        delivery.current_position = result.current_position
        delivery.destination = result.destination
        delivery.origin = result.origin
        delivery.deposit_date = result.deposit_date
        delivery.delivery_date = result.delivery_date
        delivery.last_checked_at = timezone.now()

        delivery.save(update_fields=[
            'status', 'product', 'weight', 'amount_cod',
            'current_position', 'destination', 'origin',
            'deposit_date', 'delivery_date', 'last_checked_at'
        ])

        # Update timeline if we have events
        if result.timeline:
            # Delete old timeline events from AMANA
            delivery.timeline.filter(source='amana').delete()

            # Create new timeline events
            for event in result.timeline:
                DeliveryTimelineEvent.objects.create(
                    delivery=delivery,
                    event_number=event.number,
                    event_date=event.date,
                    event_time=event.time,
                    description=event.description,
                    location=event.location,
                    source='amana'
                )

        # Update invoice delivery status if different
        if delivery.invoice:
            status_map = {
                'pending': 'pending',
                'in_transit': 'in_transit',
                'delivered': 'delivered'
            }
            new_invoice_status = status_map.get(result.status, 'pending')
            if delivery.invoice.delivery_status != new_invoice_status:
                delivery.invoice.delivery_status = new_invoice_status
                delivery.invoice.save(update_fields=['delivery_status'])

        logger.info(f"✓ Updated delivery {delivery.reference} - Status: {result.status}")
        return True

    def bulk_update_deliveries(self, deliveries=None) -> Dict[str, Any]:
        """
        Update multiple deliveries with fresh tracking data.

        Args:
            deliveries: QuerySet of Delivery objects, or None to update all non-delivered AMANA deliveries

        Returns:
            Dictionary with update statistics
        """
        from sales.models import Delivery

        if deliveries is None:
            # Get all AMANA deliveries that are not delivered
            deliveries = Delivery.objects.filter(
                delivery_method_type='amana',
                status__in=['pending', 'in_transit']
            ).exclude(tracking_number='')

        stats = {
            'total': 0,
            'updated': 0,
            'failed': 0,
            'errors': []
        }

        for delivery in deliveries:
            stats['total'] += 1

            try:
                if self.update_delivery(delivery):
                    stats['updated'] += 1
                else:
                    stats['failed'] += 1
                    stats['errors'].append(f"{delivery.tracking_number}: Update failed")
            except Exception as e:
                stats['failed'] += 1
                stats['errors'].append(f"{delivery.tracking_number}: {str(e)}")

            # Small delay between requests to avoid rate limiting
            time.sleep(0.5)

        logger.info(f"Bulk update complete: {stats['updated']}/{stats['total']} updated")
        return stats
