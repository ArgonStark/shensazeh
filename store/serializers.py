from rest_framework import serializers

from .models import Product, Category


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'image']


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    primary_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'category', 'price',
            'stock', 'primary_image_url',
        ]

    def get_primary_image_url(self, obj):
        img = obj.primary_image
        if img:
            return img.image.url
        return None
