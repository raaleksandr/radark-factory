"""The start banner: RA DARK FACTORY in block letters over a factory with smoking chimneys (change start-banner).

Printed once by run, once and dry-run right before the configuration summary. Plain printable ASCII, at most 80
columns, no trailing spaces, so it looks the same in any console and in console.log.
"""
from __future__ import annotations

BANNER = r"""
            #####    ####           #####    ####   #####   #   #
            #    #  #    #          #    #  #    #  #    #  #  #
            #####   ######          #    #  ######  #####   ###
            #   #   #    #          #    #  #    #  #   #   #  #
            #    #  #    #          #####   #    #  #    #  #   #

            ######   ####    #####  ######   ####   #####   #    #
            #       #    #  #         ##    #    #  #    #   #  #
            ####    ######  #         ##    #    #  #####     ##
            #       #    #  #         ##    #    #  #   #     ##
            #       #    #   #####    ##     ####   #    #    ##

                                     ~~~   ~~~~    ~~~
                                   (  )  (   )   (  )
                                  (    )  ) (   (    )
                                   (  )  (   )   (  )
                                    ||    | |     ||
          /|    /|    /|    /|      ||    | |     ||
         / |   / |   / |   / |      ||    | |     ||
        /  |  /  |  /  |  /  |______||____|_|_____||______
       /   | /   | /   | /   |                            |
       | [] [] [] [] [] [] [] [] []   [] [] []   ____     |
       | [] [] [] [] [] [] [] [] []   [] [] []  |    |    |
  _____|________________________________________|____|____|_____
"""[1:-1]


def lines() -> list[str]:
    """The banner's lines, top to bottom."""
    return BANNER.split("\n")
