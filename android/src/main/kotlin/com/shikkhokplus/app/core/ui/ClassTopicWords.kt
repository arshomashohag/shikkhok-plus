package com.shikkhokplus.app.core.ui

import com.shikkhokplus.app.R

/**
 * The heading over a class's topics.
 *
 * One topic field is the plan before a class is held and what was
 * covered after; the server's state says which, so only a `taken` class
 * is labelled as covered.
 *
 * @param state The class's state, as the server decided it
 * @return The string resource
 */
fun classTopicsHeading(state: CalendarState): Int =
    if (state == CalendarState.TAKEN) R.string.classday_topics_covered else R.string.family_planned_topics

/**
 * The words shown when a class has no topics.
 *
 * @param state The class's state, as the server decided it
 * @return The string resource
 */
fun classTopicsEmpty(state: CalendarState): Int =
    if (state == CalendarState.TAKEN) R.string.session_topic_unlogged else R.string.class_no_topics_planned
