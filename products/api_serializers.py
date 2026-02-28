"""
DRF serializers for RFID inventory API
"""
from rest_framework import serializers
from .models import Product, RFIDInventorySession


class ProductRFIDSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, default='')
    metal_purity_name = serializers.CharField(source='metal_purity.name', read_only=True, default='')
    main_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'reference', 'name', 'rfid_tag', 'barcode',
            'status', 'category_name', 'metal_purity_name',
            'gross_weight', 'net_weight', 'selling_price',
            'main_image_url',
        ]

    def get_main_image_url(self, obj):
        if obj.main_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.main_image.url)
            return obj.main_image.url
        return None


class RFIDInventorySessionSerializer(serializers.ModelSerializer):
    started_by_name = serializers.CharField(source='started_by.get_full_name', read_only=True, default='')
    location_name = serializers.CharField(source='location.name', read_only=True, default='')

    class Meta:
        model = RFIDInventorySession
        fields = [
            'id', 'started_at', 'completed_at', 'status',
            'started_by_name', 'location_name',
            'expected_count', 'found_count', 'missing_count',
            'scanned_tags', 'notes',
        ]
        read_only_fields = ['id', 'started_at', 'started_by_name', 'location_name']


class RFIDInventorySessionDetailSerializer(RFIDInventorySessionSerializer):
    found_products = ProductRFIDSerializer(many=True, read_only=True)
    missing_products = ProductRFIDSerializer(many=True, read_only=True)

    class Meta(RFIDInventorySessionSerializer.Meta):
        fields = RFIDInventorySessionSerializer.Meta.fields + [
            'found_products', 'missing_products',
        ]
