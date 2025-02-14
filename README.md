Fork Author: Kevin Paniagua Romero
https://www.linkedin.com/in/kevinpr/
https://cig.fi.upm.es

BayesInterpret is a computational project focused on creating interactive dashboards for interpreting and visualizing machine learning models using Dash. This fork is part of the BayesInterpret initiative, where the main goal is to apply an intuitive interface to existing implementations, making model outputs and analyses easier to understand and use.

This work is based on ideas and research from the Computational Intelligence Group (CIG) and integrates interface design with machine learning tools to enhance interpretability in a simple and practical way.

# ProbExplainer
Library to adapt and explain probabilistic models and specially aimed for Bayesian networks. 

## Why ProbExplainer?
Because there are way too many Bayesian network libraries out there, and none of them is really focused on explaining the models.
Which one to choose if you wanted to develop XAI for these models? And what is worse, at the end of the day, yoi barely need to
compute some probability queries and to access the parameters, very few methods...

So instead of limiting yourself to a specific library, you can use ProbExplainer to adapt any Bayesian network library to your needs!
But, how can I do this?

## How to use ProbExplainer
First, a bit of theory on how the library is organised
### Model submodule
In this directory, you will find abstracts implementations of necessary methods of probabilistic models to get explanations (for
instance, maximum a posteriori queries). If you want to adapt a new library, you will need to implement these methods for your concrete
probabilistic model (i.e. PyAgrum, PyBnesian, pgmpy, etc.). You only need to adapt some easy model, so don't worry! It will barely take you a morning!
### Algorithm submodule
But, what is the point of redifining these methods??? I already have them at my disposar with my "introduce concrete implementation"! 
But here is actually when the magic kicks in...

Since you redefined these methods, they can be used by a higher level interface that can also adapt other implementations. So when you
write an XAI algorithm (or any algorithm!), it can be used by other user using another library!

Speaking of which, to develop your algorithm you only need to code it in this submodule. Beware, it is forbidden to use any concrete implementations
(i.e., you cannot import adapters from the model submodule, but rather abstract classes). Otherwise, the algorithms will only work with the library you adapted 
and you will make other users very sad :(

## A collaborative library
ProbExplainer is a collaborative library by design. It is suppose to grow and grow while there is an interest for explaining Bayesian 
networks and other probabilistic models.

So please, feel free to contribute to the library! If you want to adapt a new library, you can do it and make a pull request. If you want to develop a new algorithm,
you can also do it and make a pull request. And if you have any problem, contact me and I will reach back ASAP
