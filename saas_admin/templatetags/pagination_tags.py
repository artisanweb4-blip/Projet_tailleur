from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    query = context['request'].GET.copy()
    
    for key, value in kwargs.items():
        if value is not None and value != '':
            query[key] = value
        else:
            query.pop(key, None)
            
    return query.urlencode()