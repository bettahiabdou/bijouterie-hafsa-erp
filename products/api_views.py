"""
RFID Inventory API views for Chainway C72 integration.
Token-authenticated endpoints for the Android app.
"""
from django.contrib.auth import authenticate
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Product, RFIDInventorySession
from .api_serializers import (
    ProductRFIDSerializer,
    RFIDInventorySessionSerializer,
    RFIDInventorySessionDetailSerializer,
)


def _find_product_by_epc(epc):
    """
    Find a product by scanned EPC, handling the ZPL PC-word offset.
    The ZPL ^RFW,H,1,12,1 writes 12 bytes starting at word 1 (PC word),
    so the first 2 bytes of our hex become the PC, shifting the actual EPC.
    Relationship: scanned_epc[0:20] == db_rfid_tag[4:24]
    """
    qs = Product.objects.select_related('category', 'metal_purity')
    # Try exact match first (for future correctly-encoded tags)
    product = qs.filter(rfid_tag__iexact=epc).first()
    if product:
        return product
    # Handle PC offset: match db_rfid_tag that ends with epc[:20]
    if len(epc) >= 20:
        epc_core = epc[:20]
        product = qs.filter(rfid_tag__iendswith=epc_core).first()
    return product


def _batch_find_products(epcs_upper):
    """
    Batch find products by scanned EPCs, handling the ZPL PC-word offset.
    Returns dict: {scanned_epc: Product}
    """
    qs = Product.objects.select_related('category', 'metal_purity')

    # Try exact matches first
    exact = qs.filter(rfid_tag__in=epcs_upper)
    result = {p.rfid_tag.upper(): p for p in exact}

    # For unmatched EPCs, try the PC-offset match
    unmatched = [e for e in epcs_upper if e not in result]
    if unmatched:
        # Build a map of rfid_tag_suffix -> product for offset matching
        all_products = qs.filter(
            rfid_tag__isnull=False,
        ).exclude(rfid_tag='')
        suffix_map = {}
        for p in all_products:
            if p.rfid_tag and len(p.rfid_tag) >= 24:
                suffix = p.rfid_tag[4:].upper()
                suffix_map[suffix] = p

        for epc in unmatched:
            if len(epc) >= 20:
                epc_core = epc[:20].upper()
                if epc_core in suffix_map:
                    result[epc] = suffix_map[epc_core]

    return result


@api_view(['POST'])
@permission_classes([AllowAny])
def rfid_login(request):
    """
    Authenticate and return a token for the RFID app.
    POST {username, password}
    """
    username = request.data.get('username', '')
    password = request.data.get('password', '')

    if not username or not password:
        return Response(
            {'error': 'username and password required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(username=username, password=password)
    if not user:
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    token, _ = Token.objects.get_or_create(user=user)
    return Response({
        'token': token.key,
        'user': {
            'id': user.id,
            'username': user.username,
            'name': user.get_full_name() or user.username,
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rfid_lookup(request):
    """
    Look up a single product by RFID EPC.
    GET ?epc=XXXX
    """
    epc = request.GET.get('epc', '').strip().upper()
    if not epc:
        return Response(
            {'error': 'epc parameter required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    product = _find_product_by_epc(epc)
    if product:
        serializer = ProductRFIDSerializer(product, context={'request': request})
        return Response({'found': True, 'product': serializer.data})
    return Response({'found': False, 'epc': epc})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rfid_batch_check(request):
    """
    Batch lookup: given a list of EPCs, return found/missing products and unknown EPCs.
    POST {epcs: ["AAA", "BBB", ...]}
    """
    epcs = request.data.get('epcs', [])
    if not isinstance(epcs, list) or not epcs:
        return Response(
            {'error': 'epcs must be a non-empty list'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Normalize to uppercase
    epcs_upper = [e.strip().upper() for e in epcs if isinstance(e, str)]

    # Find all matching products (handles PC-word offset)
    found_map = _batch_find_products(epcs_upper)

    found = []
    unknown = []
    for epc in epcs_upper:
        if epc in found_map:
            found.append(epc)
        else:
            unknown.append(epc)

    found_serializer = ProductRFIDSerializer(
        [found_map[e] for e in found],
        many=True,
        context={'request': request},
    )

    # Missing = available products with RFID tags that were NOT scanned
    found_ids = [p.id for p in found_map.values()]
    expected_qs = Product.objects.filter(
        status='available',
        rfid_tag__isnull=False,
    ).exclude(rfid_tag='').select_related('category', 'metal_purity')
    missing_qs = expected_qs.exclude(id__in=found_ids)

    missing_serializer = ProductRFIDSerializer(
        missing_qs,
        many=True,
        context={'request': request},
    )

    return Response({
        'found': found_serializer.data,
        'missing': missing_serializer.data,
        'unknown_epcs': unknown,
        'expected_count': expected_qs.count(),
        'found_count': len(found),
        'missing_count': missing_qs.count(),
        'unknown_count': len(unknown),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rfid_session_create(request):
    """
    Start a new RFID inventory session.
    POST {location_id?: int, notes?: str}
    """
    # Count expected available products
    expected_qs = Product.objects.filter(status='available')
    location_id = request.data.get('location_id')
    if location_id:
        expected_qs = expected_qs.filter(location_id=location_id)

    session = RFIDInventorySession.objects.create(
        started_by=request.user,
        location_id=location_id,
        expected_count=expected_qs.count(),
        notes=request.data.get('notes', ''),
    )

    serializer = RFIDInventorySessionSerializer(session)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def rfid_session_save(request, session_id):
    """
    Save/complete an inventory session.
    PUT {
        scanned_tags: [{epc, found_at}],
        status: "completed" | "cancelled",
        notes?: str
    }
    """
    try:
        session = RFIDInventorySession.objects.get(pk=session_id)
    except RFIDInventorySession.DoesNotExist:
        return Response(
            {'error': 'Session not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    scanned_tags = request.data.get('scanned_tags', [])
    new_status = request.data.get('status', 'completed')

    # Extract unique EPCs from scan
    scanned_epcs = list({
        t.get('epc', '').strip().upper()
        for t in scanned_tags
        if isinstance(t, dict) and t.get('epc')
    })

    # Find matching products (handles PC-word offset)
    found_map = _batch_find_products(scanned_epcs)
    found_products = Product.objects.filter(id__in=[p.id for p in found_map.values()])
    found_ids = set(found_products.values_list('id', flat=True))

    # Missing = expected available products not found
    expected_qs = Product.objects.filter(
        status='available',
        rfid_tag__isnull=False,
    ).exclude(rfid_tag='')
    if session.location_id:
        expected_qs = expected_qs.filter(location_id=session.location_id)

    missing_products = expected_qs.exclude(id__in=found_ids)

    # Update session
    session.scanned_tags = scanned_tags
    session.found_count = found_products.count()
    session.missing_count = missing_products.count()
    session.status = new_status
    if new_status in ('completed', 'cancelled'):
        session.completed_at = timezone.now()
    if 'notes' in request.data:
        session.notes = request.data['notes']
    session.save()

    # Set M2M relations
    session.found_products.set(found_products)
    session.missing_products.set(missing_products)

    serializer = RFIDInventorySessionDetailSerializer(session, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rfid_session_detail(request, session_id):
    """Get a single session with found/missing product details."""
    try:
        session = RFIDInventorySession.objects.get(pk=session_id)
    except RFIDInventorySession.DoesNotExist:
        return Response(
            {'error': 'Session not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = RFIDInventorySessionDetailSerializer(session, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rfid_session_list(request):
    """List all inventory sessions, most recent first."""
    sessions = RFIDInventorySession.objects.all()[:50]
    serializer = RFIDInventorySessionSerializer(sessions, many=True)
    return Response(serializer.data)
