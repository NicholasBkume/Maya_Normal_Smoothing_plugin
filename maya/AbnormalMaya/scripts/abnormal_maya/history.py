"""Bounded, branch-aware full session snapshots, independent of Maya undo."""
import copy


class History:
    def __init__(self,limit=128):
        self.limit=limit
        self.states=[]
        self.position=-1

    def push(self,state):
        state=copy.deepcopy(state)
        if self.position>=0 and self.states[self.position]==state: return
        self.states=self.states[:self.position+1]+[state]
        self.states=self.states[-self.limit:]
        self.position=len(self.states)-1

    def move(self,direction,current):
        # Capture native Maya selection/undo changes before moving local history.
        self.push(current)
        target=self.position+direction
        if target<0 or target>=len(self.states): return None
        self.position=target
        return copy.deepcopy(self.states[target])
