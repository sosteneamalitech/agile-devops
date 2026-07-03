

# Amalitech Lab 1
Final Assessment – Agile & DevOps in Practice

In this lab I was working on developing a simple ai application that can be used to generate  users stories of given project.


## Github projects



The project focuses on the backend implimentation of the project. 

I have used go lang to impliment the project as  I am comfortable with it.


# Agile Process
For the  agile board  I have used  github project which can be found below
[Github Project](https://github.com/users/sosteneamalitech/projects/1)
For the sprint planning I have used GitHub internal feature of milestone to be able to impliment the sprint, but for the sake of the implimentation of my feature I have used a sprint of  of 1 days instead of  normal 2 week, and the standup were done for every 2 hours.  and the implimentation of the project was done in 2 days. 




sudo apt update

## API

The application exposes two endpoints:

- `GET /users` returns the registered users without passwords.
- `POST /users` registers a user with `name`, `email`, and `password`.

Passwords are hashed before storage, duplicate emails return `409 Conflict`, and invalid input is rejected by FastAPI validation.

## Run

Install the project dependencies and start the app with:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Test

Run the test suite with:

```bash
pytest
```



