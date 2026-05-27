# Concepts

## WorldState
The core data model representing the state of the game world. Contains information about the team, players, rivals, and the current season.

## Resolver
The component responsible for simulating match outcomes based on player stats, decisions, and random factors. Outputs a detailed record of the match events.

## SliceConfig
Configuration settings for a game slice, including opponent, map, and seed values. Used to initialize the game scenario.

## Recap
The summary of a game slice, including match events, player performances, and post-match activities. Generated after each game slice and presented to the user.

## Loader
Handles loading the initial game state from a saved file. Ensures the game starts with a consistent and valid state.
