from eventry.asyncio import filter as f
import pytest


true_filter = f.FilterFromFunction(lambda: True)
false_filter = f.FilterFromFunction(lambda: False)
dict_filter = f.FilterFromFunction(lambda: {'injection': True})
empty_dict_filter = f.FilterFromFunction(lambda: {})


@pytest.mark.asyncio
class TestFilters:

    @pytest.mark.parametrize(
        "filter,result",
        [
            (dict_filter, True),
            (empty_dict_filter, True),

            (true_filter, True),
            (f.any_of(true_filter), True),
            (f.all_of(true_filter), True),
            (f.not_(true_filter), False),
            (~true_filter, False),

            (false_filter, False),
            (f.any_of(false_filter), False),
            (f.all_of(false_filter), False),
            (f.not_(false_filter), True),
            (~false_filter, True),

            (true_filter | true_filter, True),
            (f.any_of(true_filter, true_filter), True),

            (true_filter | false_filter, True),
            (f.any_of(true_filter, false_filter), True),

            (false_filter | true_filter, True),
            (f.any_of(false_filter, true_filter), True),

            (false_filter | false_filter, False),
            (f.any_of(false_filter, false_filter), False),

            (true_filter & true_filter, True),
            (f.all_of(true_filter, true_filter), True),

            (true_filter & false_filter, False),
            (f.all_of(true_filter, false_filter), False),

            (false_filter & true_filter, False),
            (f.all_of(false_filter, true_filter), False),

            (false_filter & false_filter, False),
            (f.all_of(false_filter, false_filter), False),
        ]
    )
    async def test_filters(self, filter, result):
        r = await filter.execute((), {})
        assert r == result


    async def test_filter_context_injection(self):
        def some_filter():
            return {'injected': True}

        filter = f.FilterFromFunction(some_filter)
        context = {}

        await filter.execute((), context)
        assert context['injected'] is True

    async def test_filter_convertion(self):
        filters = [lambda: True, lambda: False]
        results = [True, False]

        for filter, result in zip(filters, results):
            filter = f.convert_filters([filter])[0]
            r = await filter.execute((), {})
            assert r == result
