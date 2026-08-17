from django.contrib import admin

from .models import Answer, Choice, Question, Response, Survey


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ('title', 'event', 'survey_type', 'is_open', 'response_count', 'created_at')
    list_filter = ('survey_type', 'is_open')
    search_fields = ('title', 'event__title')
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text', 'survey', 'question_type', 'required')
    inlines = [ChoiceInline]


admin.site.register(Response)
admin.site.register(Answer)
