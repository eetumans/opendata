#!groovy
import groovy.json.JsonOutput
import groovy.json.JsonSlurper

pipeline {
    agent {
      label 'av'
    }

    environment {
      GITHUB_TOKEN = credentials('av-github-token')
    }
    stages {
        stage('Notify Github about pending job') {
            steps {
                notifyGithub("pending")
            }
        }
        stage('Run ansible') {
            steps {
                echo 'Running ansible...'
            }
        }
        stage('Notify Github about finished job') {
            steps {
              sh '''
                set +x
                echo $BUILD_STATUS

                if [ $BUILD_STATUS == 'success' ]
                then
                  export STATUS="success"
                else
                  export STATUS="failure"
                fi
              '''

              notifyGithub($STATUS)
            }
        }
    }
}


def notifyGithub(state){
  def githubURL = "https://api.github.com/repos/vrk-kpa/opendata/statuses/$GIT_COMMIT?access_token=$GITHUB_TOKEN"
  def payload = JsonOutput.toJson([
    state: state,
    description: "VRK Jenkins",
    target_url: "http://vrk-jenkins.eden.csc.fi/job/av/job/av-run-ansible/$BUILD_NUMBER/console"
  ])

  sh "curl -X POST -H 'Content-Type: application/json' -d \'${payload}\' ${githubURL}"
}
